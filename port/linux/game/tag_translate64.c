/*
TAG_TRANSLATE64.C

The LP64 port's tag translator (docs/linux64.md).

Tag data in a cache file is the 32-bit format: its structures have 32-bit
longs and pointers, and its pointers are the absolute addresses the blob is
loaded at — the port reserves the Xbox memory map below 4 GB, so a disk
pointer zero-extends to the right LP64 pointer. Only the layouts differ.

tag_get (cache_files.c) passes every tag through tag_translate_64, which
converts the tag's root structure to the LP64 layout once, following the
generated layout table (tag_layouts64_generated.c, tools/linux64_layout.py):
scalars copy (longs widen with their sign), pointers zero-extend, blocks
translate their elements recursively into the arena, tag_data payloads stay
in the blob.
*/

#ifdef HALO_LINUX64

/* ---------- headers */

#include "cseries.h"
#include "cseries/errors.h"
#include "memory/data.h"
#include "tag_files/tag_groups.h"
#include "tag_translate64.h"

/* ---------- constants */

/* the disk layouts of the tag plumbing structs, pinned by the 32-bit
build's asserts below */
#define TAG_BLOCK_DISK_COUNT 0x0
#define TAG_BLOCK_DISK_ADDRESS 0x4
#define TAG_BLOCK_DISK_SIZE 0xC
#define TAG_REFERENCE_DISK_GROUP_TAG 0x0
#define TAG_REFERENCE_DISK_NAME 0x4
#define TAG_REFERENCE_DISK_NAME_LENGTH 0x8
#define TAG_REFERENCE_DISK_INDEX 0xC
#define TAG_REFERENCE_DISK_SIZE 0x10
#define TAG_DATA_DISK_SIZE_FIELD 0x0
#define TAG_DATA_DISK_FLAGS 0x4
#define TAG_DATA_DISK_FILE_OFFSET 0x8
#define TAG_DATA_DISK_ADDRESS 0xC
#define TAG_DATA_DISK_SIZE 0x14

/* the translated structures live here; payloads (tag_data) stay in the
blob. A map has a few MB of structures; the LP64 layouts are at most about
twice as wide */
#define TAG_TRANSLATE_ARENA_SIZE (64 << 20)

typedef char tag_block_disk_layout_assert[HALO_LAYOUT_ASSERT_32(sizeof(struct tag_block) == TAG_BLOCK_DISK_SIZE)];
typedef char tag_reference_disk_layout_assert[HALO_LAYOUT_ASSERT_32(sizeof(struct tag_reference) == TAG_REFERENCE_DISK_SIZE)];
typedef char tag_data_disk_layout_assert[HALO_LAYOUT_ASSERT_32(sizeof(struct tag_data) == TAG_DATA_DISK_SIZE)];

/* ---------- globals */

static byte *translate_arena;
static unsigned long translate_arena_used;
static unsigned long *translate_marks; /* one bit per tag: translated */
static long translate_mark_count;
static unsigned long translate_logged_groups[64];
static long translate_logged_group_count;

/* ---------- private code */

static byte *translate_arena_alloc(
	unsigned long size)
{
	byte *result;

	if (!translate_arena)
	{
		translate_arena = malloc(TAG_TRANSLATE_ARENA_SIZE);
		translate_arena_used = 0;
	}
	if (translate_arena_used + size > TAG_TRANSLATE_ARENA_SIZE)
	{
		error(_error_silent, "linux64: the tag translation arena is full (%lu bytes)", (unsigned long)TAG_TRANSLATE_ARENA_SIZE);
		return NULL;
	}
	result = translate_arena + translate_arena_used;
	translate_arena_used += (size + 0xF) & ~0xF;
	memset(result, 0, size);
	return result;
}

static void translate_fields(
	const struct struct_map64 *map,
	const byte *src,
	byte *dst);

/* A tag_data blob can hold a whole data_array of structures (the
HaloScript syntax node pool the scenario carries, hs.c). The disk content
is the 32-bit data_array header and the 32-bit elements; the LP64 game uses
the translated pool in the arena as the live one. */
extern const struct struct_map64 *tag_helper_data_array_64(void);

static void translate_data_array(
	const struct field_map64 *field,
	const byte *src,
	byte *dst)
{
	/* the disk tag_data descriptor first */
	const byte *s = src + field->file_offset;
	struct tag_data *data = (struct tag_data *)(dst + field->mem_offset);
	const struct struct_map64 *header_map = tag_helper_data_array_64();
	const struct struct_map64 *element = field->element;
	struct data_array *translated;
	const byte *src_header;
	long index;
	long count;

	data->size = *(const long32 *)(s + TAG_DATA_DISK_SIZE_FIELD);
	data->pad = *(const ulong32 *)(s + TAG_DATA_DISK_FLAGS);
	data->file_offset = *(const long32 *)(s + TAG_DATA_DISK_FILE_OFFSET);
	data->address = (void *)(unsigned long)*(const ulong32 *)(s + TAG_DATA_DISK_ADDRESS);
	data->definition = NULL;

	if (!data->address || !header_map || !element)
		return;
	src_header = (const byte *)data->address;

	/* the header, generically. The disk header's element pointer is the
	stale original Xbox allocation; the elements follow the header
	contiguously (the tag_data's size is exactly the header plus the full
	pool). */
	translated = (struct data_array *)translate_arena_alloc(
		header_map->mem_size + (size_t)(*(const short *)(src_header + 32)) * element->mem_size);
	if (!translated)
		return;
	translate_fields(header_map, src_header, (byte *)translated);
	count = *(const short *)(src_header + 32); /* maximum_count */
	{
		const byte *src_elements = src_header + header_map->file_size;
		byte *elements = (byte *)translated + header_map->mem_size;
		for (index = 0; index < count; index++)
		{
			translate_fields(element,
				src_elements + index * element->file_size,
				elements + index * element->mem_size);
		}
		translated->data = elements;
		translated->size = (short)element->mem_size;
	}

	/* the descriptor now describes the arena's LP64 array; hs.c measures it
	against its own sizeof() expression */
	data->size = header_map->mem_size + count * element->mem_size;
	data->address = translated;
}

static void translate_block(
	const struct field_map64 *field,
	const byte *src,
	byte *dst)
{
	/* the disk layout: long count; void *address; void *definition */
	const byte *s = src + field->file_offset;
	struct tag_block *block = (struct tag_block *)(dst + field->mem_offset);
	long count = *(const long32 *)(s + TAG_BLOCK_DISK_COUNT);
	unsigned long address = *(const ulong32 *)(s + TAG_BLOCK_DISK_ADDRESS);
	long index;

	block->count = count;
	block->address = NULL;
	block->definition = NULL;
	if (count <= 0 || !address)
		return;
	if (!field->element)
	{
		/* tools/linux64_layout.py could not bind the element type. An empty
		block is safer than reading the disk layout wrongly; the game misses
		the content but stays up */
		error(_error_silent, "linux64: no layout for block %s of %ld elements",
			field->name ? field->name : "?", count);
		block->count = 0;
		return;
	}
	{
		const byte *src_elements = (const byte *)address;
		byte *elements = translate_arena_alloc(count * field->element->mem_size);

		if (!elements)
		{
			block->count = 0;
			return;
		}
		block->address = elements;
		for (index = 0; index < count; index++)
		{
			translate_fields(field->element,
				src_elements + index * field->element->file_size,
				elements + index * field->element->mem_size);
		}
	}
}

static void translate_reference(
	const struct field_map64 *field,
	const byte *src,
	byte *dst)
{
	/* the disk layout: tag group_tag; char *name; long name_length; long index */
	const byte *s = src + field->file_offset;
	struct tag_reference *reference = (struct tag_reference *)(dst + field->mem_offset);

	reference->group_tag = *(const ulong32 *)(s + TAG_REFERENCE_DISK_GROUP_TAG);
	reference->name = (char *)(unsigned long)*(const ulong32 *)(s + TAG_REFERENCE_DISK_NAME);
	reference->name_length = *(const long32 *)(s + TAG_REFERENCE_DISK_NAME_LENGTH);
	reference->index = *(const long32 *)(s + TAG_REFERENCE_DISK_INDEX);
}

static void translate_data(
	const struct field_map64 *field,
	const byte *src,
	byte *dst)
{
	/* the disk layout: long size; unsigned long flags; long file_offset;
	void *address; void *definition */
	const byte *s = src + field->file_offset;
	struct tag_data *data = (struct tag_data *)(dst + field->mem_offset);

	data->size = *(const long32 *)(s + TAG_DATA_DISK_SIZE_FIELD);
	data->pad = *(const ulong32 *)(s + TAG_DATA_DISK_FLAGS);
	data->file_offset = *(const long32 *)(s + TAG_DATA_DISK_FILE_OFFSET);
	data->address = (void *)(unsigned long)*(const ulong32 *)(s + TAG_DATA_DISK_ADDRESS);
	data->definition = NULL;
}

static void translate_scalar(
	const struct field_map64 *field,
	const byte *src,
	byte *dst)
{
	const byte *s = src + field->file_offset;
	byte *d = dst + field->mem_offset;

	if (field->file_size == field->mem_size)
	{
		memcpy(d, s, field->file_size);
		return;
	}
	/* a `long` widening 4 -> 8: sign or zero extends by the field's type
	(indices hold NONE = -1; FourCCs and flags must not) */
	if (field->file_size == 4 && field->mem_size == 8)
	{
		*(long *)d = (field->kind == F64_SCALAR_SIGNED)
			? (long)*(const long32 *)s
			: (long)*(const ulong32 *)s;
		return;
	}
	memset(d, 0, field->mem_size);
	memcpy(d, s, field->file_size < field->mem_size ? field->file_size : field->mem_size);
}

static void translate_fields(
	const struct struct_map64 *map,
	const byte *src,
	byte *dst)
{
	unsigned int index;

	for (index = 0; index < map->field_count; index++)
	{
		const struct field_map64 *field = &map->fields[index];

		switch (field->kind)
		{
		case F64_SCALAR_SIGNED:
		case F64_SCALAR_UNSIGNED:
			translate_scalar(field, src, dst);
			break;
		case F64_POINTER:
			*(void **)(dst + field->mem_offset) =
				(void *)(unsigned long)*(const ulong32 *)(src + field->file_offset);
			break;
		case F64_BLOCK:
			translate_block(field, src, dst);
			break;
		case F64_REFERENCE:
			translate_reference(field, src, dst);
			break;
		case F64_DATA:
			translate_data(field, src, dst);
			break;
		case F64_DATA_ARRAY:
			translate_data_array(field, src, dst);
			break;
		}
	}
}

/* ---------- public code */

void tag_translate_new_map_64(
	long tag_count)
{
	if (translate_marks)
	{
		free(translate_marks);
	}
	translate_mark_count = tag_count;
	translate_marks = malloc(((unsigned long)tag_count + 31) / 32 * sizeof(unsigned long));
	memset(translate_marks, 0, ((unsigned long)tag_count + 31) / 32 * sizeof(unsigned long));
	translate_arena_used = 0;
	translate_logged_group_count = 0;
}

void tag_translate_dispose_64(
	void)
{
	if (translate_marks)
	{
		free(translate_marks);
		translate_marks = NULL;
	}
	if (translate_arena)
	{
		free(translate_arena);
		translate_arena = NULL;
	}
	translate_arena_used = 0;
	translate_mark_count = 0;
}

void *tag_translate_64(
	long group_tag,
	long absolute_index,
	void *blob_address)
{
	const struct struct_map64 *map;
	byte *translated;

	if (!blob_address)
		return blob_address;
	if (absolute_index < 0 || absolute_index >= translate_mark_count)
		return blob_address;
	if (TEST_FLAG(translate_marks[absolute_index >> 5], absolute_index & 31))
		return blob_address;
	map = tag_group_layout_64(group_tag);
	if (!map)
	{
		long index;
		boolean known = FALSE;
		for (index = 0; index < translate_logged_group_count; index++)
		{
			if (translate_logged_groups[index] == (unsigned long)group_tag)
			{
				known = TRUE;
				break;
			}
		}
		if (!known && translate_logged_group_count < NUMBEROF(translate_logged_groups))
		{
			translate_logged_groups[translate_logged_group_count++] = group_tag;
			error(_error_silent, "linux64: no layout for tag group '%c%c%c%c'; the tag keeps its disk layout",
				(int)(group_tag >> 24) & 0xFF, (int)(group_tag >> 16) & 0xFF,
				(int)(group_tag >> 8) & 0xFF, (int)group_tag & 0xFF);
		}
		/* marked all the same: do not log or try again */
		SET_FLAG(translate_marks[absolute_index >> 5], absolute_index & 31, TRUE);
		return blob_address;
	}
	translated = translate_arena_alloc(map->mem_size);
	if (!translated)
		return blob_address;
	translate_fields(map, blob_address, translated);
	SET_FLAG(translate_marks[absolute_index >> 5], absolute_index & 31, TRUE);
	return translated;
}

#endif /* HALO_LINUX64 */
