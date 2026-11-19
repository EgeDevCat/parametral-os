//! Parametral AI — the desktop face of the assistant.
//!
//! What a user needs from the AI, in one window: is it allowed to do things right now, what is
//! it asking for, what has it done, and which model is behind it. The window itself holds no
//! authority: it reads the gateway through the CLI (which owns the approver key) and never
//! runs as root.
//!
//! Honest boundary: the model runtime belongs to the other half of the project. If no model is
//! configured this window says so instead of pretending to chat.

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

#[derive(Default, Clone)]
struct Approval {
    id: String,
    operation: String,
    justification: String,
    requested_by: String,
    expires_at: String,
}

#[derive(Default, Clone)]
struct AuditRow {
    seq: i64,
    method: String,
    actor: String,
    outcome: String,
}

#[derive(Default, Clone)]
struct Snapshot {
    reachable: bool,
    node: String,
    oracle: bool,
    audit_verified: bool,
    audit_head: String,
    sandboxes: usize,
    approvals: Vec<Approval>,
    audit: Vec<AuditRow>,
    error: String,
}

enum Msg {
    Snapshot(Snapshot),
    Action(String),
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Tab {
    Approvals,
    Status,
    Audit,
    Model,
}

fn run_cli(args: &[&str]) -> Result<String, String> {
    let out = Command::new("parametral")
        .args(args)
        .output()
        .map_err(|e| format!("`parametral` çalıştırılamadı: {e}"))?;
    if !out.status.success() {
        let err = String::from_utf8_lossy(&out.stderr).trim().to_string();
        let stdout = String::from_utf8_lossy(&out.stdout).trim().to_string();
        return Err(if err.is_empty() { stdout } else { err });
    }
    Ok(String::from_utf8_lossy(&out.stdout).to_string())
}

fn fetch() -> Snapshot {
    let mut snap = Snapshot::default();

    match run_cli(&["status"]) {
        Ok(raw) => match serde_json::from_str::<Value>(raw.trim()) {
            Ok(value) => {
                snap.reachable = true;
                snap.node = value.get("node_id").and_then(Value::as_str).unwrap_or("?").to_string();
                snap.oracle = value
                    .pointer("/harddeny/available")
                    .and_then(Value::as_bool)
                    .unwrap_or(false);
                snap.audit_verified = value
                    .pointer("/audit/verified")
                    .and_then(Value::as_bool)
                    .unwrap_or(false);
                snap.audit_head = value
                    .pointer("/audit/head_hash")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string();
                snap.sandboxes = value
                    .get("sandboxes")
                    .and_then(Value::as_array)
                    .map(|a| a.len())
                    .unwrap_or(0);
            }
            Err(e) => snap.error = format!("durum okunamadı: {e}"),
        },
        Err(e) => snap.error = e,
    }

    if let Ok(raw) = run_cli(&["approvals", "list", "--state-filter", "pending"]) {
        if let Ok(value) = serde_json::from_str::<Value>(raw.trim()) {
            if let Some(items) = value.get("approvals").and_then(Value::as_array) {
                for item in items {
                    let field = |key: &str| {
                        item.get(key).and_then(Value::as_str).unwrap_or("").to_string()
                    };
                    snap.approvals.push(Approval {
                        id: field("approval_id"),
                        operation: field("operation"),
                        justification: field("justification"),
                        requested_by: field("requested_by"),
                        expires_at: field("expires_at"),
                    });
                }
            }
        }
    }

    if let Ok(raw) = run_cli(&["audit", "tail", "--from-seq", "1", "--limit", "25"]) {
        if let Ok(value) = serde_json::from_str::<Value>(raw.trim()) {
            let rows = value
                .get("records")
                .and_then(Value::as_array)
                .cloned()
                .or_else(|| value.as_array().cloned())
                .unwrap_or_default();
            for row in rows.iter().rev().take(25) {
                snap.audit.push(AuditRow {
                    seq: row.get("seq").and_then(Value::as_i64).unwrap_or(0),
                    method: row.get("method").and_then(Value::as_str).unwrap_or("").to_string(),
                    actor: row.get("actor").and_then(Value::as_str).unwrap_or("").to_string(),
                    outcome: row.get("outcome").and_then(Value::as_str).unwrap_or("").to_string(),
                });
            }
        }
    }

    snap
}

struct App {
    tab: Tab,
    snap: Snapshot,
    status: String,
    status_colour: Color32,
    last_poll: Instant,
    tx: Sender<Msg>,
    rx: Receiver<Msg>,
    // model settings (Berkay's side owns the runtime; we only store where it lives)
    model_endpoint: String,
    model_name: String,
}

impl App {
    fn new() -> Self {
        let (tx, rx) = channel();
        let mut app = Self {
            tab: Tab::Approvals,
            snap: Snapshot::default(),
            status: "Bağlanıyor…".to_string(),
            status_colour: MUTED,
            last_poll: Instant::now() - Duration::from_secs(30),
            tx,
            rx,
            model_endpoint: String::new(),
            model_name: String::new(),
        };
        if let Some(cfg) = load_model_config() {
            app.model_endpoint = cfg.0;
            app.model_name = cfg.1;
        }
        app
    }

    fn poll(&self) {
        let tx = self.tx.clone();
        std::thread::spawn(move || {
            let _ = tx.send(Msg::Snapshot(fetch()));
        });
    }

    fn decide(&self, id: String, approve: bool) {
        let tx = self.tx.clone();
        std::thread::spawn(move || {
            let action = if approve { "approve" } else { "reject" };
            let msg = match run_cli(&["approvals", action, &id]) {
                Ok(_) if approve => format!("Onaylandı: {id}"),
                Ok(_) => format!("Reddedildi: {id}"),
                Err(e) => format!("Karar uygulanamadı: {e}"),
            };
            let _ = tx.send(Msg::Action(msg));
        });
    }

    fn pump(&mut self) {
        while let Ok(msg) = self.rx.try_recv() {
            match msg {
                Msg::Snapshot(snap) => {
                    self.status_colour = if snap.reachable { MUTED } else { DANGER };
                    if !snap.reachable && !snap.error.is_empty() {
                        self.status = snap.error.clone();
                    } else {
                        self.status = format!(
                            "{} sandbox · {} onay bekliyor · tier-2 {}",
                            snap.sandboxes,
                            snap.approvals.len(),
                            if snap.oracle { "bağlı" } else { "YOK" }
                        );
                    }
                    self.snap = snap;
                }
                Msg::Action(text) => {
                    self.status_colour = if text.contains("uygulanamadı") { DANGER } else { OK };
                    self.status = text;
                    self.last_poll = Instant::now() - Duration::from_secs(30);
                }
            }
            self.last_poll = Instant::now();
        }
    }
}

fn config_path() -> std::path::PathBuf {
    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".into());
    std::path::Path::new(&home).join(".config/parametral/ai.json")
}

fn load_model_config() -> Option<(String, String)> {
    let raw = std::fs::read_to_string(config_path()).ok()?;
    let value: Value = serde_json::from_str(&raw).ok()?;
    Some((
        value.get("endpoint").and_then(Value::as_str).unwrap_or("").to_string(),
        value.get("model").and_then(Value::as_str).unwrap_or("").to_string(),
    ))
}

fn save_model_config(endpoint: &str, model: &str) -> Result<(), String> {
    let path = config_path();
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir).map_err(|e| format!("klasör oluşturulamadı: {e}"))?;
    }
    let body = serde_json::json!({ "endpoint": endpoint, "model": model });
    std::fs::write(&path, serde_json::to_string_pretty(&body).unwrap())
        .map_err(|e| format!("yazılamadı: {e}"))
}

impl eframe::App for App {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.pump();
        if self.last_poll.elapsed() > Duration::from_secs(3) {
            self.poll();
            self.last_poll = Instant::now();
        }
        ctx.request_repaint_after(Duration::from_millis(800));

        egui::CentralPanel::default()
            .frame(egui::Frame::none().fill(BG).inner_margin(18.0))
            .show(ctx, |ui| {
                ui.horizontal(|ui| {
                    ui.label(RichText::new("Parametral").color(AMBER).size(22.0).strong());
                    ui.label(RichText::new("AI").color(TEXT).size(16.0));
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let dot = if self.snap.reachable { OK } else { DANGER };
                        ui.label(RichText::new("●").color(dot).size(14.0));
                        ui.label(
                            RichText::new(if self.snap.reachable { "gateway bağlı" } else { "gateway yok" })
                                .color(MUTED)
                                .size(11.0),
                        );
                    });
                });

                ui.add_space(8.0);
                ui.horizontal(|ui| {
                    for (tab, label) in [
                        (Tab::Approvals, "Onaylar"),
                        (Tab::Status, "Durum"),
                        (Tab::Audit, "Kayıtlar"),
                        (Tab::Model, "Model"),
                    ] {
                        let selected = self.tab == tab;
                        let text = RichText::new(label)
                            .color(if selected { Color32::from_rgb(26, 21, 9) } else { TEXT })
                            .size(13.0);
                        let button = egui::Button::new(text).fill(if selected { AMBER } else { CARD });
                        if ui.add(button).clicked() {
                            self.tab = tab;
                        }
                    }
                });
                ui.add_space(12.0);

                egui::ScrollArea::vertical().show(ui, |ui| match self.tab {
                    Tab::Approvals => self.approvals_tab(ui),
                    Tab::Status => self.status_tab(ui),
                    Tab::Audit => self.audit_tab(ui),
                    Tab::Model => self.model_tab(ui),
                });

                ui.with_layout(egui::Layout::bottom_up(egui::Align::LEFT), |ui| {
                    ui.label(RichText::new(&self.status).color(self.status_colour).size(11.0));
                });
            });
    }
}

impl App {
    fn approvals_tab(&mut self, ui: &mut egui::Ui) {
        if self.snap.approvals.is_empty() {
            ui.add_space(24.0);
            ui.vertical_centered(|ui| {
                ui.label(RichText::new("Bekleyen istek yok").color(TEXT).size(15.0));
                ui.label(
                    RichText::new("AI bir işlem için izin isterse burada belirir.")
                        .color(MUTED)
                        .size(11.0),
                );
            });
            return;
        }
        let mut decision: Option<(String, bool)> = None;
        for item in &self.snap.approvals {
            egui::Frame::none()
                .fill(CARD)
                .rounding(10.0)
                .inner_margin(14.0)
                .show(ui, |ui| {
                    ui.horizontal(|ui| {
                        ui.label(RichText::new(&item.operation).color(AMBER).size(15.0).strong());
                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                            ui.label(RichText::new(&item.expires_at).color(MUTED).size(10.0));
                        });
                    });
                    ui.add_space(4.0);
                    ui.label(RichText::new(&item.justification).color(TEXT).size(12.5));
                    ui.label(
                        RichText::new(format!("isteyen: {}", item.requested_by))
                            .color(MUTED)
                            .size(10.5),
                    );
                    ui.add_space(8.0);
                    ui.horizontal(|ui| {
                        if ui
                            .add(
                                egui::Button::new(
                                    RichText::new("Onayla").color(Color32::from_rgb(26, 21, 9)),
                                )
                                .fill(AMBER),
                            )
                            .clicked()
                        {
                            decision = Some((item.id.clone(), true));
                        }
                        if ui
                            .add(
                                egui::Button::new(RichText::new("Reddet").color(TEXT))
                                    .fill(Color32::from_rgb(60, 32, 30)),
                            )
                            .clicked()
                        {
                            decision = Some((item.id.clone(), false));
                        }
                    });
                });
            ui.add_space(8.0);
        }
        if let Some((id, approve)) = decision {
            self.decide(id, approve);
        }
    }

    fn status_tab(&mut self, ui: &mut egui::Ui) {
        let rows = [
            ("düğüm", self.snap.node.clone()),
            ("sandbox", self.snap.sandboxes.to_string()),
            ("tier-2 oracle", if self.snap.oracle { "bağlı".into() } else { "ERİŞİLEMİYOR".to_string() }),
            ("audit zinciri", if self.snap.audit_verified { "doğrulandı".into() } else { "BOZUK".to_string() }),
            ("audit uç", self.snap.audit_head.clone()),
        ];
        for (key, value) in rows {
            egui::Frame::none().fill(CARD).rounding(8.0).inner_margin(12.0).show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.label(RichText::new(key).color(MUTED).size(12.0));
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        ui.label(RichText::new(value).color(TEXT).size(12.5).monospace());
                    });
                });
            });
            ui.add_space(6.0);
        }
        ui.add_space(8.0);
        ui.label(
            RichText::new(
                "AI bu düğümde yalnızca sandbox içinde çalışır; her sistem işlemi gateway'den \
                 ve gerektiğinde buradaki onaydan geçer.",
            )
            .color(MUTED)
            .size(11.0),
        );
    }

    fn audit_tab(&mut self, ui: &mut egui::Ui) {
        if self.snap.audit.is_empty() {
            ui.label(RichText::new("Kayıt yok ya da audit'e erişilemiyor.").color(MUTED).size(12.0));
            return;
        }
        for row in &self.snap.audit {
            ui.horizontal(|ui| {
                ui.label(RichText::new(format!("#{}", row.seq)).color(MUTED).size(11.0).monospace());
                ui.label(
                    RichText::new(&row.method)
                        .color(if row.outcome == "ok" { TEXT } else { DANGER })
                        .size(12.0)
                        .monospace(),
                );
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    ui.label(RichText::new(&row.actor).color(MUTED).size(10.5));
                });
            });
        }
    }

    fn model_tab(&mut self, ui: &mut egui::Ui) {
        ui.label(RichText::new("Model bağlantısı").color(AMBER).size(14.0).strong());
        ui.add_space(4.0);
        ui.label(
            RichText::new(
                "Modelin kendisi bu projenin diğer yarısında (ayrı eğitiliyor). Burada yalnızca \
                 hangi uç noktada çalıştığı tutulur; gizli anahtar bu dosyaya yazılmaz.",
            )
            .color(MUTED)
            .size(11.0),
        );
        ui.add_space(10.0);

        egui::Frame::none().fill(CARD).rounding(10.0).inner_margin(14.0).show(ui, |ui| {
            ui.label(RichText::new("Uç nokta (OpenAI uyumlu)").color(MUTED).size(11.0));
            ui.add(
                egui::TextEdit::singleline(&mut self.model_endpoint)
                    .hint_text("http://127.0.0.1:8080/v1")
                    .desired_width(f32::INFINITY),
            );
            ui.add_space(8.0);
            ui.label(RichText::new("Model adı").color(MUTED).size(11.0));
            ui.add(
                egui::TextEdit::singleline(&mut self.model_name)
                    .hint_text("parametral-local")
                    .desired_width(f32::INFINITY),
            );
            ui.add_space(10.0);
            if ui
                .add(egui::Button::new(RichText::new("Kaydet").color(Color32::from_rgb(26, 21, 9))).fill(AMBER))
                .clicked()
            {
                match save_model_config(&self.model_endpoint, &self.model_name) {
                    Ok(()) => {
                        self.status = format!("model ayarı kaydedildi: {}", config_path().display());
                        self.status_colour = OK;
                    }
                    Err(e) => {
                        self.status = format!("kaydedilemedi: {e}");
                        self.status_colour = DANGER;
                    }
                }
            }
        });

        ui.add_space(10.0);
        let configured = !self.model_endpoint.is_empty();
        ui.label(
            RichText::new(if configured {
                "Bağlantı bilgisi tanımlı. Model çalışmıyorsa asistan yanıt veremez."
            } else {
                "Henüz model tanımlı değil: asistan yalnızca durum ve onay gösterir."
            })
            .color(if configured { OK } else { MUTED })
            .size(11.0),
        );
    }
}

fn main() -> eframe::Result<()> {
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([640.0, 480.0])
            .with_min_inner_size([520.0, 380.0])
            .with_title("Parametral AI"),
        ..Default::default()
    };
    eframe::run_native("Parametral AI", options, Box::new(|_cc| Ok(Box::new(App::new()))))
}
