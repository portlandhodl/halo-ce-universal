/*
RASTERIZER_XBOX_PIXEL_SHADER.H

Complete Xbox pixel-shader state shared by the backend and shader builders.
*/

#ifndef __RASTERIZER_XBOX_PIXEL_SHADER_H
#define __RASTERIZER_XBOX_PIXEL_SHADER_H
#pragma once

#include "cseries/cseries.h"

/* The fields are Xbox DWORD registers, so they are ulong32: 0xF0 bytes on
every build. Every rasterizer unit uses this one definition — a dozen used
to declare their own copy, which the LP64 port cannot afford
(docs/linux64.md). */
struct pixel_shader_definition
{
	ulong32 alpha_inputs[8];
	ulong32 final_combiner_inputs_abcd;
	ulong32 final_combiner_inputs_efg;
	ulong32 constant_0[8];
	ulong32 constant_1[8];
	ulong32 alpha_outputs[8];
	ulong32 rgb_inputs[8];
	ulong32 compare_mode;
	ulong32 final_combiner_constant_0;
	ulong32 final_combiner_constant_1;
	ulong32 rgb_outputs[8];
	ulong32 combiner_count;
	ulong32 texture_modes;
	ulong32 dot_mapping;
	ulong32 input_texture;
	ulong32 c0_mapping;
	ulong32 c1_mapping;
	ulong32 final_combiner_constants;
};

typedef char rasterizer_xbox_pixel_shader_definition_size_assert[HALO_LAYOUT_ASSERT_32(sizeof(struct pixel_shader_definition) == 0xF0)];

#endif /* __RASTERIZER_XBOX_PIXEL_SHADER_H */
