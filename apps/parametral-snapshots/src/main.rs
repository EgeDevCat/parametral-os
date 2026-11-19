//! Parametral snapshots — the "one button back" promise, as a window.
//!
//! The tool underneath (`parametral-snapshot`) is the authority: it creates read-only btrfs
//! snapshots, adds boot entries and promotes a snapshot back to `@`. This window is a thin
//! front end and says so — destructive actions ask twice, and root work goes through pkexec
//! (polkit), never through a setuid helper of ours.
//!
//! Look comes from parametral-ui so this window and the AI window are the same product.

use std::process::Command;
use std::sync::mpsc::{channel, Receiver, Sender};
use std::time::{Duration, Instant};

use eframe::egui;
use egui::RichText;
use serde_json::Value;

use parametral_ui as kit;

const TOOL: &str = "/usr/local/bin/parametral-snapshot";

#[derive(Clone, Default)]
struct Snap {
    id: String,
    label: String,
    created: String,
    root: String,
}

enum Msg {
    Listed(Vec<Snap>, String),
    Done(String, bool),
}

struct App {
    snaps: Vec<Snap>,
    label: String,
    status: String,
    status_ok: Option<bool>,
    pending_restore: Option<String>,
    last_poll: Instant,
    tx: Sender<Msg>,
    rx: Receiver<Msg>,
}

fn run(args: &[&str]) -> Result<String, String> {
    let out = Command::new(TOOL)
        .args(args)
        .output()
        .map_err(|e| format!("{TOOL} çalıştırılamadı: {e}"))?;
    if !out.status.success() {
        let err = String::from_utf8_lossy(&out.stderr).trim().to_string();
        return Err(if err.is_empty() {
            format!("komut başarısız: {}", out.status)
        } else {
            err
        });
    }
    Ok(String::from_utf8_lossy(&out.stdout).to_string())
}

/// Root-only actions go through pkexec so polkit asks the human, not us.
fn run_root(args: &[&str]) -> Result<String, String> {
    let out = Command::new("pkexec")
        .arg(TOOL)
        .args(args)
        .output()
        .map_err(|e| format!("pkexec çalıştırılamadı: {e}"))?;
    if !out.status.success() {
        let err = String::from_utf8_lossy(&out.stderr).trim().to_string();
        return Err(if err.is_empty() { "iptal edildi ya da başarısız".into() } else { err });
    }
    Ok(String::from_utf8_lossy(&out.stdout).to_string())
}

fn parse_list(raw: &str) -> Result<Vec<Snap>, String> {
    let value: Value = serde_json::from_str(raw.trim()).map_err(|e| format!("liste okunamadı: {e}"))?;
    let array = value.as_array().ok_or("beklenen biçim: dizi")?;
    Ok(array
        .iter()
        .map(|item| Snap {
            id: item.get("id").and_then(Value::as_str).unwrap_or("").to_string(),
            label: item.get("label").and_then(Value::as_str).unwrap_or("").to_string(),
            created: item.get("created").and_then(Value::as_str).unwrap_or("").to_string(),
            root: item.get("root").and_then(Value::as_str).unwrap_or("").to_string(),
        })
        .collect())
}

impl App {
    fn new(cc: &eframe::CreationContext<'_>) -> Self {
        style(&cc.egui_ctx);
        let (tx, rx) = channel();
        Self {
            snaps: Vec::new(),
            label: String::new(),
            status: "Yükleniyor…".into(),
            status_ok: None,
            pending_restore: None,
            last_poll: Instant::now() - Duration::from_secs(30),
            tx,
            rx,
        }
    }

    fn refresh(&self) {
        let tx = self.tx.clone();
        std::thread::spawn(move || {
            match run(&["list", "--json"]).and_then(|raw| parse_list(&raw)) {
                Ok(list) => {
                    let n = list.len();
                    let _ = tx.send(Msg::Listed(list, format!("{n} snapshot")));
                }
                Err(e) => {
                    let _ = tx.send(Msg::Listed(Vec::new(), e));
                }
            }
        });
    }

    fn action(&self, args: Vec<String>, ok_text: &'static str) {
        let tx = self.tx.clone();
        std::thread::spawn(move || {
            let refs: Vec<&str> = args.iter().map(String::as_str).collect();
            let needs_root = !matches!(refs.first(), Some(&"create"));
            let result = if needs_root { run_root(&refs) } else { run(&refs) };
            let (text, ok) = match result {
                Ok(_) => (ok_text.to_string(), true),
                Err(e) => (e, false),
            };
            let _ = tx.send(Msg::Done(text, ok));
        });
    }

    fn pump(&mut self) {
        while let Ok(msg) = self.rx.try_recv() {
            match msg {
                Msg::Listed(list, summary) => {
                    self.snaps = list;
                    self.status = summary;
                    self.status_ok = None;
                }
                Msg::Done(text, ok) => {
                    self.status = text;
                    self.status_ok = Some(ok);
                    self.last_poll = Instant::now() - Duration::from_secs(30);
                }
            }
            self.last_poll = Instant::now();
        }
    }
}

/// egui defaults look like a form toolkit; these few lines are what make a window feel built.
fn style(ctx: &egui::Context) {
    let mut style = (*ctx.style()).clone();
    style.visuals.panel_fill = kit::BG;
    style.visuals.window_fill = kit::BG;
    style.visuals.extreme_bg_color = kit::SURFACE;
    style.visuals.override_text_color = Some(kit::TEXT);
    style.spacing.item_spacing = egui::vec2(kit::GAP, kit::GAP);
    style.spacing.button_padding = egui::vec2(12.0, 6.0);
    style.visuals.widgets.noninteractive.bg_stroke = kit::hairline();
    style.visuals.selection.bg_fill = kit::AMBER;
    style.visuals.selection.stroke = egui::Stroke::new(1.0, kit::ON_AMBER);
    ctx.set_style(style);
}

impl eframe::App for App {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.pump();
        if self.last_poll.elapsed() > Duration::from_secs(4) {
            self.refresh();
            self.last_poll = Instant::now();
        }
        ctx.request_repaint_after(Duration::from_millis(900));

        egui::CentralPanel::default()
            .frame(egui::Frame::none().fill(kit::BG).inner_margin(kit::PAGE))
            .show(ctx, |ui| {
                kit::header(ui, "snapshots", "snapshot");

                ui.horizontal(|ui| {
                    ui.vertical(|ui| {
                        ui.label(kit::display("Snapshot'lar"));
                        ui.label(kit::meta(
                            "Bir şey bozulursa buradan geri dönülür. Kayıtlar salt-okunur; \
                             geri dönüş yeniden başlatmada uygulanır.",
                        ));
                    });
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::TOP), |ui| {
                        if kit::ghost_button(ui, "Yenile").clicked() {
                            self.refresh();
                        }
                    });
                });

                ui.add_space(kit::PAD);

                kit::panel(ui, |ui| {
                    ui.horizontal(|ui| {
                        ui.label(kit::meta("Yeni snapshot"));
                        ui.add_space(6.0);
                        ui.add(
                            egui::TextEdit::singleline(&mut self.label)
                                .hint_text("etiket (ör. kurulum-öncesi)")
                                .desired_width(240.0),
                        );
                        if kit::primary_button(ui, "Oluştur").clicked() {
                            let label = if self.label.trim().is_empty() {
                                "manuel".to_string()
                            } else {
                                self.label.trim().to_string()
                            };
                            self.action(vec!["create".into(), label], "Snapshot oluşturuldu");
                        }
                    });
                });

                kit::section(ui, "kayıtlar");

                if self.snaps.is_empty() {
                    ui.add_space(18.0);
                    ui.vertical_centered(|ui| {
                        kit::mark(ui, 42.0, kit::MUTED);
                        ui.add_space(6.0);
                        ui.label(kit::title("Henüz snapshot yok"));
                        ui.label(kit::meta("Kurulum ve uygulama işlemleri öncesi otomatik alınır."));
                    });
                }

                egui::ScrollArea::vertical().show(ui, |ui| {
                    let mut act: Option<(Vec<String>, &'static str)> = None;
                    for snap in &self.snaps {
                        let pending = self.pending_restore.as_deref() == Some(snap.id.as_str());
                        kit::hover_card(ui, |ui, hovered| {
                            ui.horizontal(|ui| {
                                ui.vertical(|ui| {
                                    let name = if snap.label.is_empty() { "etiket yok" } else { &snap.label };
                                    ui.label(RichText::new(name).size(14.0).color(
                                        if hovered { kit::AMBER } else { kit::TEXT },
                                    ).strong());
                                    ui.label(kit::mono(&snap.id));
                                });
                                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                    ui.label(kit::meta(if snap.root == "present" {
                                        &snap.created
                                    } else {
                                        "kök eksik"
                                    }));
                                });
                            });
                            ui.add_space(10.0);
                            ui.horizontal(|ui| {
                                let restore_label =
                                    if pending { "Emin misin? Geri dön" } else { "Bu ana dön" };
                                if kit::danger_button(ui, restore_label).clicked() {
                                    if pending {
                                        act = Some((
                                            vec!["promote".into(), snap.id.clone()],
                                            "Geri dönüş hazırlandı — yeniden başlatınca açılır",
                                        ));
                                    } else {
                                        self.pending_restore = Some(snap.id.clone());
                                    }
                                }
                                if kit::ghost_button(ui, "Önyükleme girdisi").clicked() {
                                    act = Some((
                                        vec!["boot-entry".into(), snap.id.clone()],
                                        "Önyükleme girdisi eklendi",
                                    ));
                                }
                                if kit::ghost_button(ui, "Sil").clicked() {
                                    act = Some((vec!["delete".into(), snap.id.clone()], "Snapshot silindi"));
                                }
                            });
                        });
                        ui.add_space(kit::GAP);
                    }
                    if let Some((args, text)) = act {
                        self.action(args, text);
                    }
                });

                ui.with_layout(egui::Layout::bottom_up(egui::Align::LEFT), |ui| {
                    kit::status_bar(ui, &self.status, self.status_ok);
                });
            });
    }
}

fn main() -> eframe::Result<()> {
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([680.0, 520.0])
            .with_min_inner_size([540.0, 400.0])
            .with_title("Parametral — snapshot"),
        ..Default::default()
    };
    eframe::run_native(
        "Parametral snapshots",
        options,
        Box::new(|cc| Ok(Box::new(App::new(cc)))),
    )
}
