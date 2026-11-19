//! Parametral approval gate.
//!
//! The AI never gets to approve its own work: the daemon verifies an Ed25519 signature made
//! with a key that lives with the seat user. This window is that human step — it lists the
//! pending requests, shows what is being asked and why, and signs the decision through the
//! `parametral` CLI (which is the component that holds the key).
//!
//! Nothing here is silent: a failed listing, a missing key or a refused decision is shown in
//! the window instead of being swallowed.

use std::process::Command;
use std::sync::mpsc::{channel, Receiver, Sender};
use std::time::{Duration, Instant};

use eframe::egui;
use egui::{Color32, RichText};
use serde_json::Value;

const BG: Color32 = Color32::from_rgb(11, 15, 20);
const CARD: Color32 = Color32::from_rgb(20, 25, 32);
const TEXT: Color32 = Color32::from_rgb(233, 228, 216);
const MUTED: Color32 = Color32::from_rgb(154, 164, 178);
const AMBER: Color32 = Color32::from_rgb(224, 169, 59);
const DANGER: Color32 = Color32::from_rgb(214, 96, 86);
const OK: Color32 = Color32::from_rgb(126, 174, 104);

#[derive(Clone, Debug)]
struct Approval {
    id: String,
    operation: String,
    justification: String,
    requested_by: String,
    expires_at: String,
    scope: String,
}

enum Msg {
    Listed(Vec<Approval>, String),
    Failed(String),
    Decided(String),
}

struct App {
    items: Vec<Approval>,
    status: String,
    status_colour: Color32,
    last_poll: Instant,
    tx: Sender<Msg>,
    rx: Receiver<Msg>,
    busy: bool,
}

fn run_cli(args: &[&str]) -> Result<String, String> {
    let output = Command::new("parametral")
        .args(args)
        .output()
        .map_err(|e| format!("`parametral` çalıştırılamadı: {e}"))?;
    if !output.status.success() {
        let err = String::from_utf8_lossy(&output.stderr).trim().to_string();
        let out = String::from_utf8_lossy(&output.stdout).trim().to_string();
        return Err(if err.is_empty() { out } else { err });
    }
    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

fn parse_list(raw: &str) -> Result<Vec<Approval>, String> {
    let value: Value = serde_json::from_str(raw.trim())
        .map_err(|e| format!("onay listesi okunamadı: {e}"))?;
    let array = value
        .get("approvals")
        .and_then(Value::as_array)
        .ok_or_else(|| "onay listesi beklenen biçimde değil".to_string())?;
    let mut out = Vec::new();
    for item in array {
        let field = |key: &str| {
            item.get(key)
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string()
        };
        out.push(Approval {
            id: field("approval_id"),
            operation: field("operation"),
            justification: field("justification"),
            requested_by: field("requested_by"),
            expires_at: field("expires_at"),
            scope: item
                .get("scope")
                .map(|s| s.to_string())
                .unwrap_or_else(|| "{}".to_string()),
        });
    }
    Ok(out)
}

impl App {
    fn new() -> Self {
        let (tx, rx) = channel();
        Self {
            items: Vec::new(),
            status: "Yükleniyor…".to_string(),
            status_colour: MUTED,
            last_poll: Instant::now() - Duration::from_secs(30),
            tx,
            rx,
            busy: false,
        }
    }

    fn spawn_refresh(&self) {
        let tx = self.tx.clone();
        std::thread::spawn(move || {
            match run_cli(&["approvals", "list", "--state-filter", "pending"])
                .and_then(|raw| parse_list(&raw))
            {
                Ok(items) => {
                    let n = items.len();
                    let _ = tx.send(Msg::Listed(items, format!("{n} bekleyen istek")));
                }
                Err(e) => {
                    let _ = tx.send(Msg::Failed(e));
                }
            }
        });
    }

    fn decide(id: String, approve: bool, tx: Sender<Msg>) {
        let action = if approve { "approve" } else { "reject" };
        std::thread::spawn(move || {
            let result = run_cli(&["approvals", action, &id]);
            let message = match result {
                Ok(_) if approve => format!("Onaylandı: {id}"),
                Ok(_) => format!("Reddedildi: {id}"),
                Err(e) => format!("Karar uygulanamadı: {e}"),
            };
            let _ = tx.send(Msg::Decided(message));
        });
    }

    fn pump(&mut self) {
        while let Ok(msg) = self.rx.try_recv() {
            self.busy = false;
            match msg {
                Msg::Listed(items, summary) => {
                    self.items = items;
                    self.status = summary;
                    self.status_colour = MUTED;
                }
                Msg::Failed(e) => {
                    self.status = e;
                    self.status_colour = DANGER;
                }
                Msg::Decided(message) => {
                    self.status_colour = if message.contains("uygulanamadı") {
                        DANGER
                    } else {
                        OK
                    };
                    self.status = message;
                }
            }
            self.last_poll = Instant::now();
        }
    }
}

impl eframe::App for App {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.pump();
        if self.last_poll.elapsed() > Duration::from_secs(3) {
            self.spawn_refresh();
            self.last_poll = Instant::now();
        }
        ctx.request_repaint_after(Duration::from_millis(700));

        egui::CentralPanel::default()
            .frame(egui::Frame::none().fill(BG).inner_margin(18.0))
            .show(ctx, |ui| {
                ui.horizontal(|ui| {
                    ui.label(RichText::new("Parametral").color(AMBER).size(22.0).strong());
                    ui.label(RichText::new("onay kapısı").color(TEXT).size(16.0));
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        if ui
                            .add(egui::Button::new(RichText::new("Yenile").color(TEXT)).fill(CARD))
                            .clicked()
                        {
                            self.spawn_refresh();
                        }
                    });
                });
                ui.add_space(4.0);
                ui.label(
                    RichText::new("AI hiçbir sistemi tek başına değiştiremez; bu pencere onun izin isteğidir.")
                        .color(MUTED)
                        .size(12.0),
                );
                ui.add_space(12.0);

                if self.items.is_empty() {
                    ui.add_space(30.0);
                    ui.vertical_centered(|ui| {
                        ui.label(RichText::new("Bekleyen istek yok").color(TEXT).size(16.0));
                        ui.label(RichText::new("AI bir işlem için izin isterse burada görünür.").color(MUTED).size(12.0));
                    });
                }

                egui::ScrollArea::vertical().show(ui, |ui| {
                    let mut decision: Option<(String, bool)> = None;
                    for item in &self.items {
                        egui::Frame::none()
                            .fill(CARD)
                            .rounding(10.0)
                            .inner_margin(14.0)
                            .show(ui, |ui| {
                                ui.horizontal(|ui| {
                                    ui.label(RichText::new(&item.operation).color(AMBER).size(16.0).strong());
                                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                        ui.label(RichText::new(&item.expires_at).color(MUTED).size(11.0));
                                    });
                                });
                                ui.add_space(6.0);
                                ui.label(RichText::new(&item.justification).color(TEXT).size(13.0));
                                ui.add_space(4.0);
                                ui.label(
                                    RichText::new(format!("isteyen: {}   kapsam: {}", item.requested_by, item.scope))
                                        .color(MUTED)
                                        .size(11.0),
                                );
                                ui.add_space(10.0);
                                ui.horizontal(|ui| {
                                    if ui
                                        .add(egui::Button::new(RichText::new("Onayla").color(Color32::from_rgb(26, 21, 9))).fill(AMBER))
                                        .clicked()
                                    {
                                        decision = Some((item.id.clone(), true));
                                    }
                                    if ui
                                        .add(egui::Button::new(RichText::new("Reddet").color(TEXT)).fill(Color32::from_rgb(60, 32, 30)))
                                        .clicked()
                                    {
                                        decision = Some((item.id.clone(), false));
                                    }
                                });
                            });
                        ui.add_space(10.0);
                    }
                    if let Some((id, approve)) = decision {
                        self.busy = true;
                        App::decide(id, approve, self.tx.clone());
                    }
                });

                ui.with_layout(egui::Layout::bottom_up(egui::Align::LEFT), |ui| {
                    ui.label(RichText::new(&self.status).color(self.status_colour).size(12.0));
                });
            });
    }
}

fn main() -> eframe::Result<()> {
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([620.0, 460.0])
            .with_min_inner_size([480.0, 320.0])
            .with_title("Parametral — onay istekleri"),
        ..Default::default()
    };
    eframe::run_native(
        "Parametral onay",
        options,
        Box::new(|_cc| Ok(Box::new(App::new()))),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    // Shaped exactly like `parametral approvals list --state-filter pending` (the fields
    // approvals.py writes): a parser that only works on hand-made fixtures would not prove
    // the window can read what the daemon produces.
    const SAMPLE: &str = r#"{
      "approvals": [
        {
          "approval_id": "apr_9f2c1a8b3d4e",
          "node_id": "local",
          "operation": "host.apply",
          "scope": {"preset": "install-package"},
          "justification": "ripgrep kurulacak",
          "requested_by": "client:ai",
          "requested_at": "2026-11-19T22:40:11Z",
          "expires_at": "2026-11-19T22:55:11Z",
          "state": "pending",
          "decided_at": null,
          "decided_by": null,
          "reason": null
        }
      ]
    }"#;

    #[test]
    fn parses_pending_list() {
        let items = parse_list(SAMPLE).expect("sample must parse");
        assert_eq!(items.len(), 1);
        assert_eq!(items[0].id, "apr_9f2c1a8b3d4e");
        assert_eq!(items[0].operation, "host.apply");
        assert_eq!(items[0].justification, "ripgrep kurulacak");
        assert_eq!(items[0].requested_by, "client:ai");
        assert!(items[0].scope.contains("install-package"));
    }

    #[test]
    fn empty_list_is_not_an_error() {
        let items = parse_list(r#"{"approvals": []}"#).expect("empty list parses");
        assert!(items.is_empty());
    }

    #[test]
    fn garbage_is_reported_not_swallowed() {
        assert!(parse_list("not json").is_err());
        assert!(parse_list(r#"{"approvals": 5}"#).is_err());
        assert!(parse_list(r#"{}"#).is_err());
    }
}
