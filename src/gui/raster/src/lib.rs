use tiny_skia::{FillRule, Paint, PathBuilder, Pixmap, Rect, Stroke, Transform};

pub struct Canvas { pixmap: Pixmap, bgra: Vec<u8> }

#[no_mangle]
pub extern "C" fn gs_canvas_new(width: u32, height: u32) -> *mut Canvas {
    if width == 0 || height == 0 || width > 2048 || height > 2048 { return std::ptr::null_mut(); }
    match Pixmap::new(width, height) {
        Some(pixmap) => Box::into_raw(Box::new(Canvas { pixmap, bgra: vec![0; width as usize * height as usize * 4] })),
        None => std::ptr::null_mut(),
    }
}

#[no_mangle]
pub unsafe extern "C" fn gs_canvas_free(canvas: *mut Canvas) {
    if !canvas.is_null() { drop(Box::from_raw(canvas)); }
}

fn paint(color: u32) -> Paint<'static> {
    let mut p = Paint::default();
    p.set_color_rgba8((color >> 24) as u8, (color >> 16) as u8, (color >> 8) as u8, color as u8);
    p.anti_alias = true;
    p
}

#[no_mangle]
pub unsafe extern "C" fn gs_canvas_ellipse(canvas: *mut Canvas, cx: f32, cy: f32,
    rx: f32, ry: f32, color: u32, filled: bool, width: f32) {
    let Some(canvas) = canvas.as_mut() else { return };
    let Some(rect) = Rect::from_xywh(cx-rx, cy-ry, rx*2.0, ry*2.0) else { return };
    let mut builder = PathBuilder::new(); builder.push_oval(rect);
    let Some(path) = builder.finish() else { return };
    if filled { canvas.pixmap.fill_path(&path,&paint(color),FillRule::Winding,Transform::identity(),None); }
    else { canvas.pixmap.stroke_path(&path,&paint(color),&Stroke { width, ..Stroke::default() },Transform::identity(),None); }
}

#[no_mangle]
pub unsafe extern "C" fn gs_canvas_path(canvas: *mut Canvas, xy: *const f32, count: u32,
    color: u32, closed: bool, filled: bool, width: f32) {
    let Some(canvas) = canvas.as_mut() else { return };
    if xy.is_null() || count < 2 || count > 256 { return; }
    let points = std::slice::from_raw_parts(xy,count as usize*2);
    if points.iter().any(|p| !p.is_finite()) { return; }
    let mut builder = PathBuilder::new(); builder.move_to(points[0],points[1]);
    for p in points[2..].chunks_exact(2) { builder.line_to(p[0],p[1]); }
    if closed { builder.close(); }
    let Some(path) = builder.finish() else { return };
    if filled { canvas.pixmap.fill_path(&path,&paint(color),FillRule::Winding,Transform::identity(),None); }
    else { canvas.pixmap.stroke_path(&path,&paint(color),&Stroke { width, ..Stroke::default() },Transform::identity(),None); }
}

#[no_mangle]
pub unsafe extern "C" fn gs_canvas_pixels(canvas: *mut Canvas) -> *const u8 {
    let Some(canvas) = canvas.as_mut() else { return std::ptr::null() };
    for (rgba,bgra) in canvas.pixmap.data().chunks_exact(4).zip(canvas.bgra.chunks_exact_mut(4)) {
        bgra.copy_from_slice(&[rgba[2],rgba[1],rgba[0],rgba[3]]);
    }
    canvas.bgra.as_ptr()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn bounded_canvas_and_premultiplied_conversion() {
        assert!(gs_canvas_new(0,10).is_null());
        assert!(gs_canvas_new(2049,10).is_null());
        unsafe {
            let c=gs_canvas_new(32,32);
            gs_canvas_ellipse(c,16.,16.,8.,8.,0xff000080,true,1.);
            let pixels=std::slice::from_raw_parts(gs_canvas_pixels(c),4096);
            let center=&pixels[(16*32+16)*4..(16*32+16)*4+4];
            assert_eq!(center,&[0,0,128,128]);
            assert_eq!(&pixels[..4],&[0,0,0,0]);
            gs_canvas_free(c);
        }
    }
}
