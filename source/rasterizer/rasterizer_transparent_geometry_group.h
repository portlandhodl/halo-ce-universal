/*
RASTERIZER_TRANSPARENT_GEOMETRY_GROUP.H

The transparent geometry sort group, defined once for all the rasterizer
units that walk it.

The original x86 source defines this structure five times
(rasterizer_transparent_geometry.c, and rasterizer_xbox_{models,widgets,
water,active_camouflage}.c), as partial views that coincide byte-for-byte on
the Xbox and validate each other's layout. The union of the widget group's
render_proc and the triangle buffer is in the original, as is the model
effect. The LP64 port (docs/linux64.md) cannot share the object across five
definitions whose pointers widen by different amounts, so they share this
one; the 32-bit build keeps the Xbox layout (the offset asserts below check
it, and the byte-matching objects do not change).
*/

#ifndef __RASTERIZER_TRANSPARENT_GEOMETRY_GROUP_H
#define __RASTERIZER_TRANSPARENT_GEOMETRY_GROUP_H
#pragma once

/* ---------- headers */

#include "cseries.h"
#include "math/real_math.h"
#include "shaders/shaders.h"
#include "rasterizer_model_types.h"
#include "rasterizer_transparent_geometry.h"

/* ---------- structures */

struct transparent_geometry_group
{
	unsigned long geometry_flags;
	long object_index;
	long source_object_index;
	struct shader *shader;
	short shader_permutation_index;
	short pad12;
	/* the widget group field set (effect_type/effect_intensity) and the
	model effect parameters share the bytes, as in the original; the effect
	is 0x28 bytes, so the union runs to 0x3C where both views resume */
	union
	{
		struct
		{
			short effect_type;
			short pad16;
			real effect_intensity;
		};
		struct render_model_effect effect;
	};
	real_vector2d model_base_map_scale;
	long dynamic_triangle_buffer_index;
	/* a NULL shader marks a widget group: rasterizer_xbox_widgets.c stores
	render_proc here and its two arguments in the next two fields */
	union
	{
		struct triangle_buffer const *triangle_buffer;
		void (*render_proc)(
			long object_index,
			long widget_index);
	};
	long first_triangle_index;
	long triangle_count;
	long dynamic_vertex_buffer_index;
	struct vertex_buffer const *vertex_buffer;
	struct bitmap_data const *lightmap;
	void const *node_matrices;
	short node_matrix_count;
	word pad66;
	struct render_lighting const *lighting;
	struct render_animation const *animation;
	real z_sort;
	real_point3d centroid;
	real_plane3d plane;
	long sorted_index;
	short previous_group_presorted_index;
	short next_group_presorted_index;
	long active_camouflage_transparent_source_object_index;
	boolean sort_last;
	boolean cortana_hack;
	byte pad9E[2];
};

typedef char transparent_geometry_group_size_assert[HALO_LAYOUT_ASSERT_32(sizeof(struct transparent_geometry_group) == 0xA0)];
typedef char transparent_geometry_group_triangle_buffer_offset_assert[HALO_LAYOUT_ASSERT_32(offsetof(struct transparent_geometry_group, triangle_buffer) == 0x48)];
typedef char transparent_geometry_group_vertex_buffer_offset_assert[HALO_LAYOUT_ASSERT_32(offsetof(struct transparent_geometry_group, vertex_buffer) == 0x58)];
typedef char transparent_geometry_group_effect_type_offset_assert[HALO_LAYOUT_ASSERT_32(offsetof(struct transparent_geometry_group, effect_type) == 0x14)];
typedef char transparent_geometry_group_effect_intensity_offset_assert[HALO_LAYOUT_ASSERT_32(offsetof(struct transparent_geometry_group, effect_intensity) == 0x18)];
typedef char transparent_geometry_group_node_matrices_offset_assert[HALO_LAYOUT_ASSERT_32(offsetof(struct transparent_geometry_group, node_matrices) == 0x60)];
typedef char transparent_geometry_group_lighting_offset_assert[HALO_LAYOUT_ASSERT_32(offsetof(struct transparent_geometry_group, lighting) == 0x68)];
typedef char transparent_geometry_group_model_base_map_scale_offset_assert[HALO_LAYOUT_ASSERT_32(offsetof(struct transparent_geometry_group, model_base_map_scale) == 0x3C)];
typedef char transparent_geometry_group_z_sort_offset_assert[HALO_LAYOUT_ASSERT_32(offsetof(struct transparent_geometry_group, z_sort) == 0x70)];
typedef char transparent_geometry_group_centroid_offset_assert[HALO_LAYOUT_ASSERT_32(offsetof(struct transparent_geometry_group, centroid) == 0x74)];
typedef char transparent_geometry_group_plane_offset_assert[HALO_LAYOUT_ASSERT_32(offsetof(struct transparent_geometry_group, plane) == 0x80)];
typedef char transparent_geometry_group_sorted_index_offset_assert[HALO_LAYOUT_ASSERT_32(offsetof(struct transparent_geometry_group, sorted_index) == 0x90)];
typedef char transparent_geometry_group_active_camouflage_offset_assert[HALO_LAYOUT_ASSERT_32(offsetof(struct transparent_geometry_group, active_camouflage_transparent_source_object_index) == 0x98)];
typedef char transparent_geometry_group_cortana_hack_offset_assert[HALO_LAYOUT_ASSERT_32(offsetof(struct transparent_geometry_group, cortana_hack) == 0x9D)];

#endif /* __RASTERIZER_TRANSPARENT_GEOMETRY_GROUP_H */
