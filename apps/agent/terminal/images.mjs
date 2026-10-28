import { stripVTControlCharacters } from "node:util";

export const MAX_IMAGE_BYTES = 8 * 1024 * 1024;
const clean = value => stripVTControlCharacters(String(value)).replace(/[\x00-\x1f\x7f-\x9f]/gu, " ");

export function imageMime(bytes) {
  if (bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))) return "image/png";
  if (bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255) return "image/jpeg";
  if (["GIF87a", "GIF89a"].includes(bytes.toString("ascii", 0, 6))) return "image/gif";
  if (bytes.toString("ascii", 0, 4) === "RIFF" && bytes.toString("ascii", 8, 12) === "WEBP") return "image/webp";
  throw new Error("Preview supports PNG, JPEG, GIF and WebP images.");
}

/** Read through the Host, including over SSH. Never open a remote path locally. */
export async function readWorkspaceImage({ request, workspaceId, path, signal }) {
  if (!path || path.startsWith("/") || path.split("/").some(part => part === "..") || /[\x00-\x1f]/u.test(path)) {
    throw new Error("Use /image <workspace-relative path>.");
  }
  signal?.throwIfAborted();
  const scope = { workspace_id: workspaceId, path };
  const { file, max_chunk_bytes } = await request("files/stat", scope);
  if (file?.kind !== "file" || !Number.isSafeInteger(file.size) || file.size <= 0 || file.size > MAX_IMAGE_BYTES) {
    throw new Error("Choose an image smaller than 8 MiB.");
  }
  if (typeof file.version !== "string" || !Number.isSafeInteger(max_chunk_bytes) || max_chunk_bytes < 1) throw new Error("Invalid image metadata");
  const chunks = [];
  let offset = 0;
  while (offset < file.size) {
    signal?.throwIfAborted();
    const length = Math.min(max_chunk_bytes, 256 * 1024, file.size - offset);
    const page = await request("files/read", { ...scope, offset, length, expected_version: file.version });
    signal?.throwIfAborted();
    if (typeof page.data_base64 !== "string" || page.data_base64.length > Math.ceil(length / 3) * 4) throw new Error("Invalid image page");
    const bytes = Buffer.from(page.data_base64, "base64");
    if (page.file?.version !== file.version || page.file?.size !== file.size || page.file?.path !== file.path
      || page.offset !== offset || !bytes.length || bytes.length > length || page.next_offset !== offset + bytes.length
      || page.eof !== (page.next_offset === file.size) || page.next_offset > file.size) throw new Error("Image changed while reading. Open it again.");
    chunks.push(bytes); offset = page.next_offset;
  }
  const bytes = Buffer.concat(chunks);
  return { type: "image", data: bytes.toString("base64"), mimeType: imageMime(bytes), filename: path };
}

/** Pi owns terminal graphics and textual fallbacks; previews never invoke a model. */
export function createImageView({ components, theme, block, filename = "Image", panel = false }) {
  const { Image, Text, getImageDimensions, truncateToWidth } = components;
  let height = 18, image, previousHeight;
  let dimensions, error, data;
  try {
    if (typeof block.data !== "string" || block.data.length > Math.ceil(MAX_IMAGE_BYTES / 3) * 4) throw new Error("Image exceeds the preview limit");
    const bytes = Buffer.from(block.data, "base64");
    // The decoder accepts whitespace and other non-base64 bytes. Never forward
    // the original string into a terminal graphics escape sequence.
    data = bytes.toString("base64");
    if (imageMime(bytes) !== block.mimeType) throw new Error("Image format does not match its content");
    dimensions = getImageDimensions(data, block.mimeType);
    if (!dimensions || !Number.isSafeInteger(dimensions.widthPx) || !Number.isSafeInteger(dimensions.heightPx)
      || dimensions.widthPx <= 0 || dimensions.heightPx <= 0 || dimensions.widthPx * dimensions.heightPx > 40_000_000) {
      throw new Error("Image dimensions are invalid or exceed 40 megapixels");
    }
  } catch (cause) { error = cause.message; }
  const label = clean(filename);
  return {
    setViewport(value) { height = Math.max(4, value); },
    invalidate() { image?.invalidate(); },
    render(width) {
      const caption = `${label}${dimensions ? ` · ${dimensions.widthPx}×${dimensions.heightPx}` : ""}`;
      const head = truncateToWidth(` ${caption}`, Math.max(1, width));
      const hint = panel ? [truncateToWidth(" Esc Back · Preview only", Math.max(1, width))] : [];
      if (error) return [head, ...new Text(`Preview unavailable: ${error}`, 1, 0).render(width), ...hint];
      if (!image || height !== previousHeight) {
        image = new Image(data, block.mimeType, { fallbackColor: text => theme.fg("muted", text) },
          { filename: label, maxWidthCells: 100, maxHeightCells: Math.max(1, height - 3) }, dimensions);
        previousHeight = height;
      }
      try {
        return [head, ...image.render(width), ...hint];
      } catch { return [head, ...new Text("Preview unavailable in this terminal.", 1, 0).render(width), ...hint]; }
    },
  };
}
