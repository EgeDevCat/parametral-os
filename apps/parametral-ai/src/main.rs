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
use egui::RichText;
use serde_json::Value;

use parametral_ui as kit;

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
                snap.oracle = value.pointer("/harddeny/available").and_then(Value::as_bool).unwrap_or(false);
                snap.audit_verified = value.pointer("/audit/verified").and_then(Value::as_bool).unwrap_or(false);
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
        Err(e) => snap.error = first_line(&e),
    }

    if let Ok(raw) = run_cli(&["approvals", "list", "--state-filter", "pending"]) {
        if let Ok(value) = serde_json::from_str::<Value>(raw.trim()) {
            if let Some(items) = value.get("approvals").and_then(Value::as_array) {
                for item in items {
                    let field = |key: &str| item.get(key).and_then(Value::as_str).unwrap_or("").to_string();
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

/// Tracebacks are long; the window shows the reason, not the whole stack.
fn first_line(text: &str) -> String {
    text.lines()
        .filter(|line| !line.trim().is_empty())
        .last()
        .unwrap_or(text)
        .trim()
        .to_string()
}

struct App {
    tab: Tab,
    snap: Snapshot,
    status: String,
    status_ok: Option<bool>,
    last_poll: Instant,
    tx: Sender<Msg>,
    rx: Receiver<Msg>,
    model_endpoint: String,
    model_name: String,
}

impl App {
    fn new(cc: &eframe::CreationContext<'_>) -> Self {
        kit::style(&cc.egui_ctx);
        let (tx, rx) = channel();
        let mut app = Self {
            tab: Tab::Approvals,
            snap: Snapshot::default(),
            status: "Bağlanıyor…".to_string(),
            status_ok: None,
            last_poll: Instant::now() - Duration::from_secs(30),
            tx,
            rx,
            model_endpoint: String::new(),
            model_name: String::new(),
        };
        if let Some((endpoint, model)) = load_model_config() {
            app.model_endpoint = endpoint;
            app.model_name = model;
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
                Err(e) => format!("Karar uygulanamadı: {}", first_line(&e)),
            };
            let _ = tx.send(Msg::Action(msg));
        });
    }

    fn pump(&mut self) {
        while let Ok(msg) = self.rx.try_recv() {
            match msg {
                Msg::Snapshot(snap) => {
                    self.status_ok = if snap.reachable { None } else { Some(false) };
                    self.status = if snap.reachable {
                        format!(
                            "{} sandbox · {} onay bekliyor · tier-2 {}",
                            snap.sandboxes,
                            snap.approvals.len(),
                            if snap.oracle { "bağlı" } else { "erişilemiyor" }
                        )
                    } else {
                        snap.error.clone()
                    };
                    self.snap = snap;
                }
                Msg::Action(text) => {
                    self.status_ok = Some(!text.contains("uygulanamadı"));
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
            .frame(egui::Frame::none().fill(kit::BG).inner_margin(kit::PAGE))
            .show(ctx, |ui| {
                kit::header(ui, "ai", "AI");

                ui.horizontal_top(|ui| {
                    // navigation rail, not tabs: the window has four places to be
                    ui.vertical(|ui| {
                        ui.set_width(150.0);
                        kit::mark(ui, 44.0, kit::AMBER);
                        ui.add_space(10.0);
                        for (tab, label) in [
                            (Tab::Approvals, "Onaylar"),
                            (Tab::Status, "Durum"),
                            (Tab::Audit, "Kayıtlar"),
                            (Tab::Model, "Model"),
                        ] {
                            if kit::nav_item(ui, label, self.tab == tab).clicked() {
                                self.tab = tab;
                            }
                        }
                        ui.add_space(10.0);
                        let (colour, text) = if self.snap.reachable {
                            (kit::OK, "gateway bağlı")
                        } else {
                            (kit::DANGER, "gateway yok")
                        };
                        ui.label(RichText::new(format!("● {text}")).color(colour).size(10.5));
                    });

                    ui.add_space(kit::PAD);

                    ui.vertical(|ui| match self.tab {
                        Tab::Approvals => self.approvals_tab(ui),
                        Tab::Status => self.status_tab(ui),
                        Tab::Audit => self.audit_tab(ui),
                        Tab::Model => self.model_tab(ui),
                    });
                });

                ui.with_layout(egui::Layout::bottom_up(egui::Align::LEFT), |ui| {
                    kit::status_bar(ui, &self.status, self.status_ok);
                });
            });
    }
}

impl App {
    fn approvals_tab(&mut self, ui: &mut egui::Ui) {
        ui.label(kit::display("Onay istekleri"));
        ui.label(kit::meta(
            "AI hiçbir sistemi tek başına değiştiremez. Onayladığında karar Ed25519 ile imzalanır.",
        ));
        kit::section(ui, "bekleyen");

        if self.snap.approvals.is_empty() {
            ui.add_space(16.0);
            ui.vertical_centered(|ui| {
                kit::mark(ui, 40.0, kit::MUTED);
                ui.add_space(6.0);
                ui.label(kit::title("Bekleyen istek yok"));
                ui.label(kit::meta("AI bir işlem için izin isterse burada görünür."));
            });
            return;
        }

        let mut decision: Option<(String, bool)> = None;
        for item in &self.snap.approvals {
            kit::card(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.label(RichText::new(&item.operation).size(14.0).color(kit::AMBER).strong());
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        ui.label(kit::meta(&item.expires_at));
                    });
                });
                ui.add_space(4.0);
                ui.label(kit::body(&item.justification));
                ui.label(kit::mono(format!("isteyen: {}", item.requested_by)));
                ui.add_space(10.0);
                ui.horizontal(|ui| {
                    if kit::primary_button(ui, "Onayla").clicked() {
                        decision = Some((item.id.clone(), true));
                    }
                    if kit::danger_button(ui, "Reddet").clicked() {
                        decision = Some((item.id.clone(), false));
                    }
                });
            });
            ui.add_space(kit::GAP);
        }
        if let Some((id, approve)) = decision {
            self.decide(id, approve);
        }
    }

    fn status_tab(&mut self, ui: &mut egui::Ui) {
        ui.label(kit::display("Durum"));
        ui.label(kit::meta("Bu düğümde AI'ın ne yapabildiğinin özeti."));
        kit::section(ui, "düğüm");

        let rows = [
            ("düğüm", self.snap.node.clone(), None),
            ("sandbox", self.snap.sandboxes.to_string(), None),
            (
                "tier-2 oracle",
                if self.snap.oracle { "bağlı".into() } else { "ERİŞİLEMİYOR".to_string() },
                Some(self.snap.oracle),
            ),
            (
                "audit zinciri",
                if self.snap.audit_verified { "doğrulandı".into() } else { "BOZUK".to_string() },
                Some(self.snap.audit_verified),
            ),
            ("audit uç", self.snap.audit_head.clone(), None),
        ];
        for (key, value, state) in rows {
            kit::card(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.label(kit::meta(key));
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let colour = match state {
                            Some(true) => kit::OK,
                            Some(false) => kit::DANGER,
                            None => kit::TEXT,
                        };
                        ui.label(RichText::new(value).color(colour).size(12.5).monospace());
                    });
                });
            });
            ui.add_space(6.0);
        }
    }

    fn audit_tab(&mut self, ui: &mut egui::Ui) {
        ui.label(kit::display("Kayıtlar"));
        ui.label(kit::meta("AI'ın yaptığı her işlem hash zincirine yazılır."));
        kit::section(ui, "son işlemler");

        if self.snap.audit.is_empty() {
            ui.label(kit::meta("Kayıt yok ya da audit'e erişilemiyor."));
            return;
        }
        for row in &self.snap.audit {
            ui.horizontal(|ui| {
                ui.label(kit::mono(format!("#{}", row.seq)));
                ui.label(
                    RichText::new(&row.method)
                        .size(12.0)
                        .monospace()
                        .color(if row.outcome == "ok" { kit::TEXT } else { kit::DANGER }),
                );
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    ui.label(kit::meta(&row.actor));
                });
            });
        }
    }

    fn model_tab(&mut self, ui: &mut egui::Ui) {
        ui.label(kit::display("Model"));
        ui.label(kit::meta(
            "Modelin kendisi bu projenin diğer yarısında eğitiliyor. Burada yalnızca nerede \
             çalıştığı tutulur; gizli anahtar bu dosyaya yazılmaz.",
        ));
        kit::section(ui, "bağlantı");

        kit::card(ui, |ui| {
            ui.label(kit::meta("Uç nokta (OpenAI uyumlu)"));
            ui.add(
                egui::TextEdit::singleline(&mut self.model_endpoint)
                    .hint_text("http://127.0.0.1:8080/v1")
                    .desired_width(f32::INFINITY),
            );
            ui.add_space(6.0);
            ui.label(kit::meta("Model adı"));
            ui.add(
                egui::TextEdit::singleline(&mut self.model_name)
                    .hint_text("parametral-local")
                    .desired_width(f32::INFINITY),
            );
            ui.add_space(10.0);
            if kit::primary_button(ui, "Kaydet").clicked() {
                match save_model_config(&self.model_endpoint, &self.model_name) {
                    Ok(()) => {
                        self.status = format!("model ayarı kaydedildi: {}", config_path().display());
                        self.status_ok = Some(true);
                    }
                    Err(e) => {
                        self.status = format!("kaydedilemedi: {e}");
                        self.status_ok = Some(false);
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
                "Henüz model tanımlı değil: bu pencere yalnızca durum ve onay gösterir."
            })
            .size(11.0)
            .color(if configured { kit::OK } else { kit::MUTED }),
        );
    }
}

fn main() -> eframe::Result<()> {
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([760.0, 520.0])
            .with_min_inner_size([620.0, 420.0])
            .with_title("Parametral AI"),
        ..Default::default()
    };
    eframe::run_native(
        "Parametral AI",
        options,
        Box::new(|cc| Ok(Box::new(App::new(cc)))),
    )
}
