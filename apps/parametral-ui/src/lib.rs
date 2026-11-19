//! Parametral UI kit — the design language our own apps share.
//!
//! The first versions of these apps were raw egui: every label the same weight, cards with no
//! edge, buttons that looked like form controls. That reads as a prototype. This crate exists
//! so all first-party windows use one type scale, one spacing rhythm, one card language and
//! the same vector mark, instead of each app inventing its own.

use eframe::egui;
use egui::{Color32, FontId, Rect, Response, RichText, Stroke, Ui, Vec2};

// ---------------------------------------------------------------- palette
pub const BG: Color32 = Color32::from_rgb(11, 15, 20);
pub const SURFACE: Color32 = Color32::from_rgb(18, 23, 30);
pub const CARD: Color32 = Color32::from_rgb(23, 29, 37);
pub const CARD_HOVER: Color32 = Color32::from_rgb(30, 37, 47);
pub const TEXT: Color32 = Color32::from_rgb(233, 228, 216);
pub const MUTED: Color32 = Color32::from_rgb(154, 164, 178);
pub const FAINT: Color32 = Color32::from_rgb(107, 114, 128);
pub const AMBER: Color32 = Color32::from_rgb(224, 169, 59);
pub const AMBER_DIM: Color32 = Color32::from_rgb(120, 92, 34);
pub const DANGER: Color32 = Color32::from_rgb(214, 96, 86);
pub const OK: Color32 = Color32::from_rgb(126, 174, 104);
pub const ON_AMBER: Color32 = Color32::from_rgb(26, 21, 9);

// ---------------------------------------------------------------- metrics
pub const RADIUS: f32 = 12.0;
pub const PAD: f32 = 16.0;
pub const GAP: f32 = 8.0;
pub const PAGE: f32 = 22.0;

pub fn edge() -> Stroke {
    Stroke::new(1.0, Color32::from_rgba_unmultiplied(224, 169, 59, 28))
}

pub fn hairline() -> Stroke {
    Stroke::new(1.0, Color32::from_rgba_unmultiplied(154, 164, 178, 34))
}

// ---------------------------------------------------------------- type scale
pub fn display(text: impl Into<String>) -> RichText {
    RichText::new(text.into()).size(26.0).color(TEXT).strong()
}

pub fn title(text: impl Into<String>) -> RichText {
    RichText::new(text.into()).size(17.0).color(TEXT)
}

pub fn body(text: impl Into<String>) -> RichText {
    RichText::new(text.into()).size(13.0).color(TEXT)
}

pub fn meta(text: impl Into<String>) -> RichText {
    RichText::new(text.into()).size(11.0).color(MUTED)
}

pub fn mono(text: impl Into<String>) -> RichText {
    RichText::new(text.into()).size(11.0).color(FAINT).monospace()
}

/// Small uppercase section label with letterspacing — the cheapest way to look designed.
pub fn section(ui: &mut Ui, text: &str) {
    ui.add_space(GAP);
    let mut job = egui::text::LayoutJob::single_section(
        format!(" {}", text.to_uppercase()),
        egui::TextFormat {
            font_id: FontId::proportional(10.0),
            color: FAINT,
            extra_letter_spacing: 1.6,
            ..Default::default()
        },
    );
    job.wrap.max_width = ui.available_width();
    ui.label(job);
    ui.add_space(4.0);
}

// ---------------------------------------------------------------- surfaces
pub fn card<R>(ui: &mut Ui, add: impl FnOnce(&mut Ui) -> R) -> R {
    egui::Frame::none()
        .fill(CARD)
        .stroke(edge())
        .rounding(RADIUS)
        .inner_margin(egui::Margin::same(PAD))
        .show(ui, add)
        .inner
}

pub fn panel<R>(ui: &mut Ui, add: impl FnOnce(&mut Ui) -> R) -> R {
    egui::Frame::none()
        .fill(SURFACE)
        .rounding(RADIUS)
        .inner_margin(egui::Margin::same(PAD))
        .show(ui, add)
        .inner
}

/// A card that reacts to the pointer — used for list rows.
pub fn hover_card<R>(ui: &mut Ui, add: impl FnOnce(&mut Ui, bool) -> R) -> R {
    let id = ui.next_auto_id();
    let rect = ui.available_rect_before_wrap();
    let sense = ui.interact(
        Rect::from_min_size(rect.min, Vec2::new(rect.width(), 1.0)),
        id,
        egui::Sense::hover(),
    );
    let hovered = sense.hovered();
    let fill = if hovered { CARD_HOVER } else { CARD };
    egui::Frame::none()
        .fill(fill)
        .stroke(edge())
        .rounding(RADIUS)
        .inner_margin(egui::Margin::symmetric(PAD, PAD - 2.0))
        .show(ui, |ui| add(ui, hovered))
        .inner
}

// ---------------------------------------------------------------- controls
pub fn primary_button(ui: &mut Ui, label: &str) -> Response {
    ui.add(
        egui::Button::new(RichText::new(label).size(12.5).color(ON_AMBER).strong())
            .fill(AMBER)
            .rounding(9.0)
            .min_size(Vec2::new(0.0, 30.0)),
    )
}

pub fn danger_button(ui: &mut Ui, label: &str) -> Response {
    ui.add(
        egui::Button::new(RichText::new(label).size(12.5).color(Color32::from_rgb(248, 200, 194)))
            .fill(Color32::from_rgb(58, 30, 28))
            .stroke(Stroke::new(1.0, Color32::from_rgba_unmultiplied(214, 96, 86, 90)))
            .rounding(9.0)
            .min_size(Vec2::new(0.0, 30.0)),
    )
}

pub fn ghost_button(ui: &mut Ui, label: &str) -> Response {
    ui.add(
        egui::Button::new(RichText::new(label).size(12.5).color(TEXT))
            .fill(Color32::TRANSPARENT)
            .stroke(hairline())
            .rounding(9.0)
            .min_size(Vec2::new(0.0, 30.0)),
    )
}

/// Navigation rail entry: a wide, quiet row that shows selection with an amber bar.
pub fn nav_item(ui: &mut Ui, label: &str, selected: bool) -> Response {
    let height = 34.0;
    let (rect, response) =
        ui.allocate_exact_size(Vec2::new(ui.available_width(), height), egui::Sense::click());
    let hovered = response.hovered();
    if selected || hovered {
        ui.painter().rect_filled(
            rect.shrink2(Vec2::new(0.0, 1.0)),
            9.0,
            if selected { CARD_HOVER } else { CARD },
        );
    }
    if selected {
        let bar = Rect::from_min_size(
            rect.left_top() + Vec2::new(3.0, 8.0),
            Vec2::new(3.0, height - 16.0),
        );
        ui.painter().rect_filled(bar, 2.0, AMBER);
    }
    ui.painter().text(
        rect.left_center() + Vec2::new(16.0, 0.0),
        egui::Align2::LEFT_CENTER,
        label,
        FontId::proportional(13.0),
        if selected { TEXT } else { MUTED },
    );
    response
}

// ---------------------------------------------------------------- status
pub fn status_bar(ui: &mut Ui, text: &str, good: Option<bool>) {
    let (dot, colour) = match good {
        Some(true) => ("●", OK),
        Some(false) => ("●", DANGER),
        None => ("●", FAINT),
    };
    ui.horizontal(|ui| {
        ui.label(RichText::new(dot).color(colour).size(9.0));
        ui.label(RichText::new(text).color(MUTED).size(11.0));
    });
}

pub fn header(ui: &mut Ui, app: &str, page: &str) {
    ui.horizontal(|ui| {
        mark(ui, 22.0, AMBER);
        ui.add_space(8.0);
        ui.label(RichText::new("Parametral").color(TEXT).size(15.0).strong());
        ui.label(RichText::new("·").color(FAINT).size(15.0));
        ui.label(RichText::new(page).color(AMBER).size(15.0));
        let _ = app;
    });
    ui.add_space(12.0);
    let rect = ui.available_rect_before_wrap();
    ui.painter().hline(rect.x_range(), rect.top(), hairline());
    ui.add_space(12.0);
}

// ---------------------------------------------------------------- the mark
/// The gauge, drawn as vectors so it scales cleanly and needs no asset file.
pub fn mark(ui: &mut Ui, size: f32, colour: Color32) -> Response {
    let (rect, response) = ui.allocate_exact_size(Vec2::splat(size), egui::Sense::hover());
    paint_mark(ui.painter(), rect, colour, 0.45);
    response
}

pub fn paint_mark(painter: &egui::Painter, rect: Rect, colour: Color32, alpha: f32) {
    let c = rect.center();
    let r = rect.width() * 0.42;
    let tick = Color32::from_rgba_unmultiplied(colour.r(), colour.g(), colour.b(), (alpha * 255.0) as u8);
    // twelve ticks around the dial
    for i in 0..12 {
        let angle = std::f32::consts::TAU * (i as f32) / 12.0 - std::f32::consts::FRAC_PI_2;
        let inner = Vec2::new(angle.cos(), angle.sin()) * r * 0.78;
        let outer = Vec2::new(angle.cos(), angle.sin()) * r;
        painter.line_segment([c + inner, c + outer], Stroke::new(rect.width() * 0.055, tick));
    }
    // amber arc + needle
    let arc_r = r * 0.62;
    painter.circle_stroke(c, arc_r, Stroke::new(rect.width() * 0.05, tick));
    let needle = Vec2::new(0.62, -0.62) * arc_r;
    painter.line_segment([c, c + needle], Stroke::new(rect.width() * 0.07, AMBER));
    painter.circle_filled(c, rect.width() * 0.06, AMBER);
}

fn _unused(_: FontId) {}


/// egui's defaults look like a form toolkit. One call at startup makes any window ours.
pub fn style(ctx: &egui::Context) {
    let mut style = (*ctx.style()).clone();
    style.visuals.panel_fill = BG;
    style.visuals.window_fill = BG;
    style.visuals.extreme_bg_color = SURFACE;
    style.visuals.override_text_color = Some(TEXT);
    style.spacing.item_spacing = egui::vec2(GAP, GAP);
    style.spacing.button_padding = egui::vec2(12.0, 6.0);
    style.visuals.widgets.noninteractive.bg_stroke = hairline();
    style.visuals.selection.bg_fill = AMBER;
    style.visuals.selection.stroke = Stroke::new(1.0, ON_AMBER);
    style.visuals.widgets.inactive.weak_bg_fill = CARD;
    style.visuals.widgets.hovered.weak_bg_fill = CARD_HOVER;
    ctx.set_style(style);
}
