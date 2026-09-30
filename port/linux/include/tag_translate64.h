/*
TAG_TRANSLATE64.H

The LP64 port's tag translator (docs/linux64.md): the layout table's types
(the table itself is generated: tag_layouts64_generated.c) and the
translator's entry points. Included by game-flagged units; the field kinds
and the disk offsets of the tag plumbing structs are part of the disk
format, not of this build.
*/

#ifndef __HALO_LINUX64_TAG_TRANSLATE_H
#define __HALO_LINUX64_TAG_TRANSLATE_H
#ifdef HALO_LINUX64

/* ---------- the generated layout table */

enum field_map64_kind
{
	/* a scalar, wider in memory than on disk only for `long` (4 -> 8) */
	F64_SCALAR_SIGNED = 0,
	F64_SCALAR_UNSIGNED = 1,
	/* a pointer into the tag blob: 32-bit on disk, zero-extends (the blob
	sits in the reserved Xbox memory map below 4 GB) */
	F64_POINTER = 2,
	/* the tag plumbing structs; their disk layouts are in tag_translate64.c */
	F64_BLOCK = 3,
	F64_REFERENCE = 4,
	F64_DATA = 5,
	/* a tag_data whose bytes are a data_array of the element's structures
	(the HaloScript node pool) — the header and each element translate */
	F64_DATA_ARRAY = 6,
};

struct struct_map64;

struct field_map64
{
	unsigned int file_offset;
	unsigned int file_size;
	unsigned int mem_offset;
	unsigned int mem_size;
	unsigned int kind;
	const struct struct_map64 *element; /* F64_BLOCK: the element's layout; NULL if unknown */
	const char *name; /* "<struct>.<field>", for the "no layout" log */
};

struct struct_map64
{
	const char *name;
	unsigned int file_size;
	unsigned int mem_size;
	unsigned int field_count;
	const struct field_map64 *fields;
};

/* the root layout of a tag group ('scnr', ...), or NULL if the port does
not cover the group yet */
const struct struct_map64 *tag_group_layout_64(unsigned long group_tag);

/* ---------- the translator (tag_translate64.c) */

/* the translator's per-map state (the translated-mark bitmap, sized by the
tag count): called from tag_cache_translate_header_and_instances_64 */
void tag_translate_new_map_64(long tag_count);

/* frees it: scenario_tags_unload */
void tag_translate_dispose_64(void);

/* The LP64 address of a tag's root structure: the blob's, translated once,
per group layout. absolute_index is the tag index's low 16 bits. Returns
blob_address unchanged for groups without a layout (logged once per group)
or when already translated. */
void *tag_translate_64(long group_tag, long absolute_index, void *blob_address);

#endif /* HALO_LINUX64 */
#endif /* __HALO_LINUX64_TAG_TRANSLATE_H */
