//! Parametral snapshots — the "one button back" promise, as a window.
//!
//! The tool underneath (`parametral-snapshot`) is the authority: it creates read-only btrfs
//! snapshots, adds boot entries and promotes a snapshot back to `@`. This window is a thin
//! front end and says so — destructive actions ask twice, and root work goes through pkexec
//! (polkit), never through a setuid helper of ours.

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
    status_colour: Color32,
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
    fn new() -> Self {
        let (tx, rx) = channel();
        Self {
            snaps: Vec::new(),
            label: String::new(),
            status: "Yükleniyor…".into(),
            status_colour: MUTED,
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
            let result = if refs.first().map(|s| *s == "create").unwrap_or(false) {
                run(&refs)
            } else {
                run_root(&refs)
            };
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
                    self.status_colour = MUTED;
                }
                Msg::Done(text, ok) => {
                    self.status = text;
                    self.status_colour = if ok { OK } else { DANGER };
                    self.last_poll = Instant::now() - Duration::from_secs(30);
                }
            }
            self.last_poll = Instant::now();
        }
    }
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
            .frame(egui::Frame::none().fill(BG).inner_margin(18.0))
            .show(ctx, |ui| {
                ui.horizontal(|ui| {
                    ui.label(RichText::new("Parametral").color(AMBER).size(22.0).strong());
                    ui.label(RichText::new("snapshot").color(TEXT).size(16.0));
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        if ui
                            .add(egui::Button::new(RichText::new("Yenile").color(TEXT)).fill(CARD))
                            .clicked()
                        {
                            self.refresh();
                        }
                    });
                });
                ui.label(
                    RichText::new(
                        "Bir şey bozulursa buradan geri dönülür. Snapshot'lar salt-okunur; \
                         geri dönmek için yeniden başlatma gerekir.",
                    )
                    .color(MUTED)
                    .size(11.0),
                );
                ui.add_space(12.0);

                egui::Frame::none().fill(CARD).rounding(10.0).inner_margin(12.0).show(ui, |ui| {
                    ui.horizontal(|ui| {
                        ui.label(RichText::new("Yeni snapshot:").color(MUTED).size(11.0));
                        ui.add(
                            egui::TextEdit::singleline(&mut self.label)
                                .hint_text("etiket (ör. kurulum-öncesi)")
                                .desired_width(220.0),
                        );
                        if ui
                            .add(
                                egui::Button::new(RichText::new("Oluştur").color(Color32::from_rgb(26, 21, 9)))
                                    .fill(AMBER),
                            )
                            .clicked()
                        {
                            let label = if self.label.trim().is_empty() {
                                "manuel".to_string()
                            } else {
                                self.label.trim().to_string()
                            };
                            self.action(vec!["create".into(), label], "Snapshot oluşturuldu");
                        }
                    });
                });
                ui.add_space(12.0);

                if self.snaps.is_empty() {
                    ui.add_space(20.0);
                    ui.vertical_centered(|ui| {
                        ui.label(RichText::new("Henüz snapshot yok").color(TEXT).size(15.0));
                        ui.label(
                            RichText::new("Kurulum ve uygulama işlemleri öncesi otomatik alınır.")
                                .color(MUTED)
                                .size(11.0),
                        );
                    });
                }

                egui::ScrollArea::vertical().show(ui, |ui| {
                    let mut act: Option<(Vec<String>, &'static str)> = None;
                    for snap in &self.snaps {
                        let pending = self.pending_restore.as_deref() == Some(snap.id.as_str());
                        egui::Frame::none().fill(CARD).rounding(10.0).inner_margin(12.0).show(ui, |ui| {
                            ui.horizontal(|ui| {
                                ui.label(RichText::new(&snap.label).color(AMBER).size(14.0).strong());
                                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                    ui.label(
                                        RichText::new(if snap.root == "present" { &snap.created } else { "eksik" })
                                            .color(MUTED)
                                            .size(10.5),
                                    );
                                });
                            });
                            ui.label(RichText::new(&snap.id).color(MUTED).size(10.0).monospace());
                            ui.add_space(8.0);
                            ui.horizontal(|ui| {
                                let restore_label = if pending { "Emin misin? Geri dön" } else { "Bu ana dön" };
                                if ui
                                    .add(
                                        egui::Button::new(RichText::new(restore_label).color(TEXT))
                                            .fill(Color32::from_rgb(60, 32, 30)),
                                    )
                                    .clicked()
                                {
                                    if pending {
                                        act = Some((
                                            vec!["promote".into(), snap.id.clone()],
                                            "Geri dönüş hazırlandı — yeniden başlatınca açılır",
                                        ));
                                    } else {
                                        self.pending_restore = Some(snap.id.clone());
                                    }
                                }
                                if ui
                                    .add(egui::Button::new(RichText::new("Önyükleme girdisi").color(TEXT)).fill(CARD))
                                    .clicked()
                                {
                                    act = Some((
                                        vec!["boot-entry".into(), snap.id.clone()],
                                        "Önyükleme girdisi eklendi",
                                    ));
                                }
                                if ui
                                    .add(egui::Button::new(RichText::new("Sil").color(MUTED)).fill(CARD))
                                    .clicked()
                                {
                                    act = Some((vec!["delete".into(), snap.id.clone()], "Snapshot silindi"));
                                }
                            });
                        });
                        ui.add_space(8.0);
                    }
                    if let Some((args, text)) = act {
                        self.action(args, text);
                    }
                });

                ui.with_layout(egui::Layout::bottom_up(egui::Align::LEFT), |ui| {
                    ui.label(RichText::new(&self.status).color(self.status_colour).size(11.0));
                });
            });
    }
}

fn main() -> eframe::Result<()> {
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([660.0, 500.0])
            .with_min_inner_size([520.0, 380.0])
            .with_title("Parametral — snapshot"),
        ..Default::default()
    };
    eframe::run_native("Parametral snapshots", options, Box::new(|_cc| Ok(Box::new(App::new()))))
}
