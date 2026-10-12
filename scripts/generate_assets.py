import os
from PIL import Image, ImageDraw

def generate_ripsync_icon(target_ico_path: str, target_png_path: str):
    """
    Renders high-resolution RipSync icon and saves it as .ico (with multiple mipmaps) and .png.
    """
    os.makedirs(os.path.dirname(os.path.abspath(target_ico_path)), exist_ok=True)

    sizes = [256, 128, 64, 48, 32, 16]
    images = []

    for size in sizes:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        scale = size / 64.0
        pad = int(4 * scale)
        r = int(12 * scale)
        
        # Rounded rectangle background
        bg_color = (61, 89, 161, 255)      # #3d59a1
        border_color = (122, 162, 247, 255) # #7aa2f7
        outline_w = max(1, int(2 * scale))

        draw.rounded_rectangle(
            [pad, pad, size - pad, size - pad],
            radius=r,
            fill=bg_color,
            outline=border_color,
            width=outline_w
        )

        # Download arrow
        arrow_color = (255, 255, 255, 255)

        # Arrow stem: rect from (26, 14) to (38, 32)
        stem_x1 = int(26 * scale)
        stem_y1 = int(14 * scale)
        stem_x2 = int(38 * scale)
        stem_y2 = int(32 * scale)
        draw.rectangle([stem_x1, stem_y1, stem_x2, stem_y2], fill=arrow_color)

        # Arrow head: polygon (18, 32), (46, 32), (32, 48)
        head_pts = [
            (int(18 * scale), int(32 * scale)),
            (int(46 * scale), int(32 * scale)),
            (int(32 * scale), int(48 * scale)),
        ]
        draw.polygon(head_pts, fill=arrow_color)

        images.append(img)

    # Save highest resolution as PNG
    images[0].save(target_png_path, format="PNG")

    # Save multi-size ICO
    images[0].save(
        target_ico_path,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[1:]
    )
    print(f"Generated ICO: {target_ico_path}")
    print(f"Generated PNG: {target_png_path}")

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ico_path = os.path.join(base_dir, "resources", "ripsync.ico")
    png_path = os.path.join(base_dir, "resources", "ripsync.png")
    generate_ripsync_icon(ico_path, png_path)

