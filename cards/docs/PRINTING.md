# Printing

Status: specification only; the engine is built in **M1** (`lib/imposition`).

Key rules (from the brief): units in PDF points (1 mm = 2.834645669 pt; 1 in = 72 pt); page
size exactly the sheet size (A4 595.28 × 841.89 pt, Letter 612 × 792 pt); never auto-fit;
`PrintScaling = None`; one PDF page = one physical sheet side as fed to the printer.

| Fold      | Sheet     | Page 1                                                                     | Page 2                                         | Duplex       |
| --------- | --------- | -------------------------------------------------------------------------- | ---------------------------------------------- | ------------ |
| half-side | landscape | L = BACK 0°, R = FRONT 0°                                                  | L = INSIDE_LEFT 0°, R = INSIDE_RIGHT 0°        | short edge   |
| half-top  | portrait  | bottom = FRONT 0°, top = BACK 180°                                         | top = INSIDE_TOP 0°, bottom = INSIDE_BOTTOM 0° | short edge   |
| quarter   | portrait  | BR = FRONT 0°, BL = BACK 0°, TR = INSIDE_LEFT 180°, TL = INSIDE_RIGHT 180° | —                                              | single-sided |
| flat      | portrait  | card centred, 3 mm bleed, crop marks                                       | optional back                                  | long edge    |

Finished sizes, margins, fold marks, the dual ruler and the calibration flow will be
documented here as they are implemented and tested.
