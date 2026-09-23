/** Shared, zero-request hover/focus preview for map picker buttons. */

import { mapThumb } from "./charts.js";

function finite(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function details(map) {
  const width = finite(map?.width);
  const height = finite(map?.height);
  if (!width || !height) return "preview unavailable locally";
  const parts = [`${width}×${height}`];
  const walls = finite(map?.walls);
  const ore = finite(map?.ore);
  if (walls !== null) parts.push(`${walls} walls`);
  if (ore !== null) parts.push(`${ore} ore`);
  return parts.join(" · ");
}

function meta(map) {
  const body = document.createElement("div");
  body.className = "run-map-preview-meta";
  const name = document.createElement("span");
  name.className = "run-map-preview-name";
  name.textContent = String(map?.name || "map");
  const dims = document.createElement("span");
  dims.className = "run-map-preview-dims";
  dims.textContent = details(map);
  body.append(name, dims);
  return body;
}

/**
 * Append one reusable popup to `parent` and bind any number of map buttons.
 * Map geometry is already present in `/api/maps`; showing it never fetches.
 */
export function createMapPreview(parent, { size = 220 } = {}) {
  const preview = document.createElement("aside");
  preview.className = "run-map-preview";
  preview.setAttribute("aria-hidden", "true");
  preview.hidden = true;
  parent.appendChild(preview);

  let previewedMap = null;
  let previewedTheme = "";

  function hide() {
    preview.hidden = true;
  }

  function place(chip) {
    const anchor = chip.getBoundingClientRect();
    const box = preview.getBoundingClientRect();
    const margin = 8;
    const gap = 8;
    const rightRoom = window.innerWidth - anchor.right - gap - margin;
    const leftRoom = anchor.left - gap - margin;
    let left;
    let top;

    if (rightRoom >= box.width) {
      left = anchor.right + gap;
      top = anchor.top + (anchor.height - box.height) / 2;
    } else if (leftRoom >= box.width) {
      left = anchor.left - box.width - gap;
      top = anchor.top + (anchor.height - box.height) / 2;
    } else {
      left = anchor.left + (anchor.width - box.width) / 2;
      const below = anchor.bottom + gap;
      top = below + box.height <= window.innerHeight - margin
        ? below
        : anchor.top - box.height - gap;
    }

    left = Math.min(
      Math.max(margin, left),
      Math.max(margin, window.innerWidth - box.width - margin),
    );
    top = Math.min(
      Math.max(margin, top),
      Math.max(margin, window.innerHeight - box.height - margin),
    );
    preview.style.left = `${Math.round(left)}px`;
    preview.style.top = `${Math.round(top)}px`;
  }

  function show(map, chip) {
    const theme = document.documentElement.dataset.theme || "";
    if (previewedMap !== map || previewedTheme !== theme) {
      previewedMap = map;
      previewedTheme = theme;
      preview.replaceChildren(
        mapThumb(map, { size, grid: false }),
        meta(map),
      );
    }
    preview.hidden = false;
    place(chip);
  }

  function bind(chip, map) {
    chip.addEventListener("mouseenter", () => show(map, chip));
    chip.addEventListener("mouseleave", hide);
    chip.addEventListener("focus", () => show(map, chip));
    chip.addEventListener("blur", hide);
    return chip;
  }

  window.addEventListener("scroll", hide, true);
  window.addEventListener("resize", hide);

  function destroy() {
    window.removeEventListener("scroll", hide, true);
    window.removeEventListener("resize", hide);
    preview.remove();
  }

  return { bind, destroy, hide };
}
