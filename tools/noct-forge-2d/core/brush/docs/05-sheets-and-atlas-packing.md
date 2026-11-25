# Sprite Sheets and Atlas Packing

**Purpose.** Combine several assets into one image with a companion JSON file that maps each asset name to its rectangle. This reduces texture switches in the game and keeps related frames together.

**Flags.** The export flags are listed by `npm run export -- --help`. That output is the single source for them. This guide covers only how to choose between the modes.

---

## 1. Two packing modes

- **Grid** (`--grid`): every cell has the same size. The sheet grows by row first, and `--cols` can fix the column count. Every position is predictable from its index.
- **Compact** (`--compact`): rectangles of different sizes are packed to minimize the total area, with no overlap. Positions come from the packer, not from an index.

Both are deterministic: the same inputs give the same layout.

---

## 2. Choosing a mode

| Content | Mode | Reason |
| :--- | :--- | :--- |
| Animation frames (walk, attack, idle) | Grid | Uniform cells keep the pivot in the same place, so frames swap without a jump. |
| Tiles and terrain | Grid | A tile index maps to a row and column directly: `col = id % cols`, `row = Math.floor(id / cols)`. |
| Icons of mixed sizes (badges, cards, buttons) | Compact | Small assets do not waste the space of large ones. |
| Anything that must be indexed by position | Grid | Compact positions are not predictable by index. |

**Recommendation.** Use grid for anything the game addresses by index, and compact for independent art of varied sizes. Mixing them in one sheet wastes space and makes lookups harder.

---

## 3. The companion JSON

The JSON has two top-level keys. `meta` describes the sheet (project, mode, size, gap, count). `frames` is keyed by asset name, and each entry gives `x`, `y`, `width` and `height` inside the sheet.

Use the asset name as the key in the game. Do not depend on the order of entries, which changes when assets are added.

The format follows the common frame-map convention used by Pixi.js, Godot, Unity and Phaser. Pass `--no-json` only when the engine reads positions another way.

---

## 4. Packing in code

`@core` exports `packGrid` and `packCompact`. Both take rectangle items and a gap and return the placed positions and the sheet size. Use them when the layout must be computed in game code, such as a runtime atlas. For build-time sheets, the export command is enough.

---

## 5. Quick decision table

| Situation | Recommended | Avoid | Reason |
| :--- | :--- | :--- | :--- |
| Walk cycle | Grid, with `--cols` set to the frame count | Compact | Frames must share a cell so the pivot stays put. |
| Map tileset | Grid | Compact | Tile lookup by index. |
| Inventory icons | Compact | Grid | Avoids empty space around small icons. |
| Engine reads by name | Keep the JSON | `--no-json` | The name map is the contract. |
