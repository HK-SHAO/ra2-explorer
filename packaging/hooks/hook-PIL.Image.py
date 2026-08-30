# RA2 Explorer reads PCX and emits PNG. Avoid bundling unrelated AVIF, WebP,
# JPEG, font, color-management and GUI extensions into the local web app.
hiddenimports = ["PIL.PcxImagePlugin", "PIL.PngImagePlugin"]
