//! parametral-calculator — the first first-party Parametral application.
//!
//! Deliberately small: one window, a display, a keypad, the same soft palette as the
//! rest of the system. It exists to prove the pipeline (Rust → binary → .desktop →
//! app menu) before we add the bigger tools.

use eframe::egui;
use egui::{Color32, FontId, RichText};

const BG: Color32 = Color32::from_rgb(13, 15, 18);
const CARD: Color32 = Color32::from_rgb(25, 29, 36);
const INK: Color32 = Color32::from_rgb(242, 237, 228);
const MUTED: Color32 = Color32::from_rgb(142, 135, 123);
const AMBER: Color32 = Color32::from_rgb(224, 169, 59);
const ON_AMBER: Color32 = Color32::from_rgb(26, 21, 9);

#[derive(Default)]
struct Calculator {
    entry: String,
    history: Vec<String>,
    error: Option<String>,
}

impl Calculator {
    fn push_digit(&mut self, d: char) {
        if self.entry == "0" {
            self.entry.clear();
        }
        if self.entry.len() < 24 {
            self.entry.push(d);
        }
    }

    fn push_op(&mut self, op: char) {
        if self.entry.is_empty() {
            return;
        }
        let last = self.entry.chars().last().unwrap();
        if "+-*/".contains(last) {
            self.entry.pop();
        }
        self.entry.push(op);
    }

    fn clear(&mut self) {
        self.entry.clear();
        self.error = None;
    }

    fn backspace(&mut self) {
        self.entry.pop();
    }

    fn evaluate(&mut self) {
        match eval(&self.entry) {
            Ok(v) => {
                let shown = if v.fract() == 0.0 && v.abs() < 1e15 {
                    format!("{}", v as i64)
                } else {
                    format!("{:.10}", v).trim_end_matches('0').trim_end_matches('.').to_string()
                };
                self.history.push(format!("{} = {}", self.entry, shown));
                if self.history.len() > 6 {
                    self.history.remove(0);
                }
                self.entry = shown;
                self.error = None;
            }
            Err(e) => self.error = Some(e),
        }
    }
}

/// Tiny recursive-descent evaluator: + - * / and parentheses, no dependencies.
fn eval(src: &str) -> Result<f64, String> {
    let mut s = src.to_string();
    if !s.chars().any(|c| c.is_ascii_digit()) {
        return Err("boş ifade".into());
    }
    while s.ends_with(['+', '-', '*', '/']) {
        s.pop();
    }
    let tokens: Vec<char> = s.chars().filter(|c| !c.is_whitespace()).collect();
    let mut pos = 0usize;
    let value = parse_expr(&tokens, &mut pos)?;
    if pos != tokens.len() {
        return Err("beklenmeyen karakter".into());
    }
    if !value.is_finite() {
        return Err("tanımsız sonuç".into());
    }
    Ok(value)
}

fn parse_expr(t: &[char], i: &mut usize) -> Result<f64, String> {
    let mut v = parse_term(t, i)?;
    while *i < t.len() && (t[*i] == '+' || t[*i] == '-') {
        let op = t[*i];
        *i += 1;
        let rhs = parse_term(t, i)?;
        v = if op == '+' { v + rhs } else { v - rhs };
    }
    Ok(v)
}

fn parse_term(t: &[char], i: &mut usize) -> Result<f64, String> {
    let mut v = parse_atom(t, i)?;
    while *i < t.len() && (t[*i] == '*' || t[*i] == '/') {
        let op = t[*i];
        *i += 1;
        let rhs = parse_atom(t, i)?;
        if op == '/' && rhs == 0.0 {
            return Err("sıfıra bölme".into());
        }
        v = if op == '*' { v * rhs } else { v / rhs };
    }
    Ok(v)
}

fn parse_atom(t: &[char], i: &mut usize) -> Result<f64, String> {
    if *i >= t.len() {
        return Err("eksik sayı".into());
    }
    if t[*i] == '(' {
        *i += 1;
        let v = parse_expr(t, i)?;
        if *i >= t.len() || t[*i] != ')' {
            return Err("kapanmayan parantez".into());
        }
        *i += 1;
        return Ok(v);
    }
    let start = *i;
    while *i < t.len() && (t[*i].is_ascii_digit() || t[*i] == '.') {
        *i += 1;
    }
    if start == *i {
        return Err("beklenmeyen karakter".into());
    }
    let s: String = t[start..*i].iter().collect();
    s.parse::<f64>().map_err(|_| "geçersiz sayı".into())
}

impl eframe::App for Calculator {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        let mut visuals = egui::Visuals::dark();
        visuals.panel_fill = BG;
        visuals.window_fill = BG;
        visuals.override_text_color = Some(INK);
        ctx.set_visuals(visuals);

        egui::CentralPanel::default().frame(egui::Frame::none().fill(BG).inner_margin(18.0)).show(ctx, |ui| {
            ui.horizontal(|ui| {
                ui.label(RichText::new("Parametral").size(20.0).color(AMBER));
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    ui.label(RichText::new("hesap makinesi").size(13.0).color(MUTED));
                });
            });
            ui.add_space(10.0);

            // display — fixed height, right-aligned, history above the value
            egui::Frame::none()
                .fill(CARD)
                .rounding(14.0)
                .inner_margin(egui::Margin::same(16.0))
                .show(ui, |ui| {
                    ui.set_width(ui.available_width());
                    ui.set_height(86.0);
                    ui.with_layout(egui::Layout::top_down(egui::Align::Max), |ui| {
                        let text = if self.entry.is_empty() {
                            "0".to_string()
                        } else {
                            self.entry.clone()
                        };
                        ui.label(RichText::new(text).size(34.0).color(INK).monospace());
                        ui.add_space(4.0);
                        if let Some(err) = &self.error {
                            ui.label(
                                RichText::new(err)
                                    .size(14.0)
                                    .color(Color32::from_rgb(224, 138, 122)),
                            );
                        } else if let Some(last) = self.history.last() {
                            ui.label(RichText::new(last).size(14.0).color(MUTED));
                        }
                    });
                });

            ui.add_space(12.0);

            let keys: [[&str; 4]; 5] = [
                ["C", "(", ")", "/"],
                ["7", "8", "9", "*"],
                ["4", "5", "6", "-"],
                ["1", "2", "3", "+"],
                ["DEL", "0", ".", "="],
            ];

            ui.spacing_mut().item_spacing = egui::vec2(6.0, 6.0);

            for row in keys {
                ui.horizontal(|ui| {
                    for k in row {
                        let is_op = "+-*/=".contains(k) && k != "=";
                        let is_eq = k == "=";
                        let fill = if is_eq { AMBER } else if is_op { CARD } else { CARD };
                        let fg = if is_eq { ON_AMBER } else if is_op { AMBER } else { INK };

                        let w = (ui.available_width() - 18.0) / 4.0;
                        let btn = egui::Button::new(RichText::new(k).size(20.0).color(fg))
                            .fill(fill)
                            .rounding(12.0)
                            .min_size(egui::vec2(w, 54.0));

                        if ui.add(btn).clicked() {
                            match k {
                                "C" => self.clear(),
                                "DEL" => self.backspace(),
                                "=" => self.evaluate(),
                                "(" | ")" => self.entry.push_str(k),
                                "." => {
                                    if !self.entry.contains('.') || self.entry.ends_with(['+', '-', '*', '/']) {
                                        self.entry.push('.');
                                    }
                                }
                                _ if k.chars().next().unwrap().is_ascii_digit() => {
                                    self.push_digit(k.chars().next().unwrap())
                                }
                                _ => self.push_op(k.chars().next().unwrap()),
                            }
                        }
                    }
                });
                ui.add_space(6.0);
            }
        });
    }
}

fn main() -> eframe::Result<()> {
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([360.0, 520.0])
            .with_min_inner_size([320.0, 460.0])
            .with_title("Parametral Hesap"),
        ..Default::default()
    };
    eframe::run_native(
        "Parametral Hesap",
        options,
        Box::new(|_cc| Ok(Box::new(Calculator::default()))),
    )
}

#[cfg(test)]
mod tests {
    use super::eval;

    #[test]
    fn arithmetic_and_precedence() {
        assert_eq!(eval("2+3*4").unwrap(), 14.0);
        assert_eq!(eval("(2+3)*4").unwrap(), 20.0);
        assert_eq!(eval("10/4").unwrap(), 2.5);
        assert_eq!(eval("7-2-1").unwrap(), 4.0);
    }

    #[test]
    fn rejects_bad_input() {
        assert!(eval("1/0").is_err());
        assert!(eval("2+").is_ok()); // trailing operator is trimmed
        assert!(eval("((2)").is_err());
        assert!(eval("abc").is_err());
    }
}
