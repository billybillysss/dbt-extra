# Logo and icons

The selected design is **Modular joint / Lagoon**: two interlocking modules in
teal (`#0D9488`) and sky blue (`#38BDF8`), separated by a transparent stepped seam.
Both background variants preserve this palette and the maintainer-supplied paths.

![Selected Modular joint icon](assets/dbt-extra-mark.svg)

## Assets

| File | Variant |
| --- | --- |
| [Square icon](assets/dbt-extra-mark.svg) | Light backgrounds; README fallback. |
| [Square icon, dark variant](assets/dbt-extra-mark-dark.svg) | Dark backgrounds; selected by the README picture element. |
| [Single-color icon](assets/dbt-extra-mark-mono.svg) | Dark navy monochrome. |

All assets have transparent backgrounds and a `128 × 128` viewBox. Preserve the
aspect ratio when resizing. They contain accessible titles/descriptions and
vector paths without scripts, images, external fonts or external resources.

The README combines the approved icon with a text **dbt-extra** title. The old
slbt horizontal wordmark is deliberately not reused or relabeled.

Use alt text such as `dbt-extra — Modular joint icon` when embedding the mark.
Update `tests/test_logo.py` when adding approved variants; preserve geometry and
the Lagoon palette rather than redrawing the icon during a code migration.

These files are included under the project's [MIT license](../LICENSE).
