# ruff: noqa: E501 -- encoded float32 tables are intentionally kept intact.

from __future__ import annotations

import base64
import struct

# Westwood's indexed normal vectors as documented by the OpenRA engine. Keeping
# the float32 payload encoded avoids hundreds of opaque numeric source lines.
# Source: https://github.com/OpenRA/OpenRA/blob/bleed/OpenRA.Mods.Cnc/Traits/World/VoxelNormalsPalette.cs
_TS_NORMALS = "rtQrP31BSz5r1Ta/pg6KPtiaFT+i7kO/kBMmvaWhxj3dlH6/pIoSv2g9vL3hlVC/voMvvh+dEr83OE2/EqG5Pq8im77pnmG/53JPP3Wssr5U//C+B+rUPc9McD8mVKi+femlvnpxFj/Ryj2/fQVNv+dQrj46PPy+FF4qv+ATF792+um+JCmhPoqRTb8AjgG/N/54P6uzGj6GyTS+jScuPxcqLz8nhIa+5iMFvzLpUz/biFe+TS52vwpMN77Y1VS+c4KGvsr8b7/04Wm+3/pgPi+neL++n7o9rn5sP5F+a75vt5w+/u+ovSx9eD9rSWc+E4AXv9RgMj8Kgs8+M+BsvyCzuz4i4sY9OX40vwYSML/T+TA+kX47P4gsLr+Vfde85utaPzbJvz6KdLc+2C3yPo4jVj9HrI0+bOvHveJzJz+4BEA/rHRnvxZqHb7nHMw+ggBZvsmrW7+Seu8+4A4APwGmLL8DCAs/WaQVPzrK4b2GyE0/W+/fPhnH6D6poEY/ndYtvaGiqj3j4H4/6KMYv0hqYT6ho0U/CacBv5JAy7539EM/e4aQPYv69L4sEWA/"
_RA2_NORMALS = "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"


def _decode(encoded: str) -> tuple[tuple[float, float, float], ...]:
    values = tuple(value[0] for value in struct.iter_unpack("<f", base64.b64decode(encoded)))
    return tuple(
        (values[index], values[index + 1], values[index + 2])
        for index in range(0, len(values), 3)
    )


TS_NORMALS = _decode(_TS_NORMALS)
RA2_NORMALS = _decode(_RA2_NORMALS)


def voxel_normal(index: int, normals_mode: int) -> tuple[float, float, float]:
    table = RA2_NORMALS if normals_mode == 4 else TS_NORMALS
    if not 0 <= index < len(table):
        return (0.0, 0.0, 1.0)
    return table[index]


__all__ = ["RA2_NORMALS", "TS_NORMALS", "voxel_normal"]
