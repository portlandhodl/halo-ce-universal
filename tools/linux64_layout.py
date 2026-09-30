#!/usr/bin/env python3
"""Generates the LP64 tag layout table (docs/linux64.md).

The 32-bit build (build/linux/halo) loads tag data zero-copy, so the DWARF
layouts of its tag structures ARE the disk layouts. The LP64 build's DWARF
gives the memory layouts. This tool reads both, walks from each known tag
group's root structure, and emits port/linux/game/tag_layouts64_generated.c:
the field maps the runtime translator (port/linux/game/tag_translate64.c)
uses to convert a tag from its disk layout to its LP64 layout at load.

Usage: python tools/linux64_layout.py   (after `ninja linux linux64`)

Needs pyelftools. Block element bindings are mined from the
TAG_BLOCK_GET_ELEMENT call sites; where a block field's element type cannot
be mined, or mines ambiguously, BLOCK_OVERRIDES binds it by hand:
(parent struct, field) or bare field name -> element struct.
"""

import re
import sys
from collections import defaultdict
from pathlib import Path

from elftools.elf.elffile import ELFFile

BUILD32 = Path("build/linux/halo")
BUILD64 = Path("build/linux64/halo")
OUTPUT = Path("port/linux/game/tag_layouts64_generated.c")

# tag group fourcc -> root structure (extend as the port covers more groups;
# docs/linux64.md)
GROUP_ROOTS = {
    "scnr": "scenario",
    "sbsp": "structure_bsp",
    "matg": "game_globals",
    # the UI tree (the menu)
    "hudg": "hud_globals_definition",
    "DeLa": "ui_widget_definition",
    "unhi": "unit_hud_interface_definition",
    "font": "font_header",
    "ustr": "string_list",
    "bitm": "bitmap_group",
    "snd!": "sound_definition",
    "lsnd": "looping_sound_definition",
    "snde": "sound_environment_definition",
    "str#": "string_list",
    "colo": "color_table_definition",
    "wphi": "weapon_hud_interface_definition",
    "vcky": "virtual_keyboard_definition",
    "mode": "model",
    "lens": "lens_flare_definition",
    "sky ": "sky",
    "fog ": "fog_definition",
    "antr": "animation_graph",
    # object definitions share the base object prefix
    "scen": "object_definition",
    "bipd": "object_definition",
    "vehi": "object_definition",
    "item": "object_definition",
    "weap": "object_definition",
    "eqip": "object_definition",
    "garb": "object_definition",
    "proj": "object_definition",
    "mach": "object_definition",
    "ctrl": "object_definition",
    "lifi": "object_definition",
    "plac": "object_definition",
    "ssce": "object_definition",
    "devi": "object_definition",
    # the shaders (partial per-unit views, merged from the DWARF)
    "senv": "shader_environment_definition",
    "soso": "shader_model_definition",
    "schi": "shader_transparent_chicago_definition",
    "sotr": "shader_transparent_generic_definition",
    "swat": "shader_transparent_water_definition",
    "sgla": "shader_transparent_glass_definition",
    "smet": "shader_transparent_meter_definition",
    "spla": "shader_transparent_plasma_definition",
    "seff": "shader_effect_definition",
}

# (parent struct, field) or bare field name -> element structure
BLOCK_OVERRIDES = {
    ("scenario", "players"): "player_starting_location",
    ("scenario", "ai_conversations"): "scenario_conversation_definition",
    ("scenario", "hs_source_files"): "hs_source_file",
    ("scenario", "bsp_switch_trigger_volumes"): "scenario_bsp_switch_trigger_volume",
    ("encounter_definition", "player_starting_locations"): "encounter_player_starting_location",
    ("game_globals", "interface_tag_references"): "interface_tag_references_definition",
    ("bitmap_group", "bitmaps"): "bitmap_data",
    ("bitmap_group", "sequences"): "bitmap_group_sequence",
    ("font_header", "characters"): "font_character",
    ("font_character_table", "character_indices"): "short",
    ("color_table_definition", "colors"): "color_table_color",
    ("game_globals", "sounds"): "tag_reference",
    ("game_globals", "cheat_powerups"): "tag_reference",
    ("game_globals_multiplayer_information", "sounds"): "tag_reference",
    ("collision_bsp", "surfaces"): "collision_surface",
    ("collision_bsp", "edges"): "collision_edge",
    ("collision_bsp", "vertices"): "collision_vertex",
    ("collision_bsp", "leaves"): "collision_leaf",
    ("collision_bsp", "bsp2d_references"): "bsp2d_reference",
    ("bsp3d", "nodes"): "bsp3d_node",
    ("bsp3d", "planes"): "real_plane3d",
    ("bsp2d", "nodes"): "bsp2d_node",
    ("looping_sound_definition", "tracks"): "looping_sound_track",
    ("multitexture_overlay_hud_element_definition", "functions"): "multitexture_overlay_hud_element_effector_definition",
    ("bitmap_group_sequence", "sprites"): "bitmap_group_sprite",
    ("leaf_portal", "vertices"): "real_point3d",
    # scenario placements and their palettes
    ("scenario", "scenery"): "scenario_scenery_datum",
    ("scenario", "bipeds"): "scenario_biped_datum",
    ("scenario", "vehicles"): "scenario_vehicle",
    ("scenario", "equipment"): "scenario_equipment_datum",
    ("scenario", "weapons"): "scenario_weapon_datum",
    ("scenario", "machines"): "scenario_machine_datum",
    ("scenario", "controls"): "scenario_control_datum",
    ("scenario", "light_fixtures"): "scenario_light_fixture_datum",
    ("scenario", "sound_scenery"): "scenario_sound_scenery_datum",
    ("scenario", "scenery_palette"): "scenario_object_palette_entry",
    ("scenario", "biped_palette"): "scenario_object_palette_entry",
    ("scenario", "vehicle_palette"): "scenario_object_palette_entry",
    ("scenario", "equipment_palette"): "scenario_object_palette_entry",
    ("scenario", "weapon_palette"): "scenario_object_palette_entry",
    ("scenario", "machine_palette"): "scenario_object_palette_entry",
    ("scenario", "control_palette"): "scenario_object_palette_entry",
    ("scenario", "light_fixtures_palette"): "scenario_object_palette_entry",
    ("scenario", "sound_scenery_palette"): "scenario_object_palette_entry",
    ("scenario", "ai_actor_palette"): "tag_reference",
    ("scenario", "detail_object_collection_palette"): "tag_reference",
    ("scenario", "predicted_ui_resources"): "predicted_resource",
    ("game_globals_player_control", "look_function"): "real",
    ("virtual_keyboard_definition", "keys"): "virtual_keyboard_key",
    ("sky", "animations"): "sky_animation",
    ("model", "markers"): "model_marker",
    ("model", "shaders"): "model_shader_reference",
    ("model_geometry", "parts"): "model_geometry_part",
    ("model_region", "permutations"): "model_region_permutation",
    ("warning_sounds"): "hud_sound_definition",
    ("overlays", "items"): "weapon_hud_overlay_item",
    ("crosshairs", "items"): "weapon_hud_crosshair_item",
    ("sound_pitch_range", "permutations"): "sound_permutation",
    ("ui_widget_definition", "event_handlers"): "ui_widget_event_handler_reference",
    ("ui_widget_definition", "child_widgets"): "ui_widget_child_reference",
    ("ui_widget_definition", "conditional_widgets"): "ui_widget_conditional_reference",
    ("ui_widget_definition", "game_data_inputs"): "ui_widget_game_data_input_reference",
    ("ui_widget_definition", "search_and_replace_functions"): "ui_widget_search_and_replace_reference",
    ("structure_bsp", "nodes"): "byte_rectangle3d",
    ("structure_bsp", "clusters"): "structure_cluster",
    ("structure_bsp", "pathfinding_surfaces"): "byte",
    ("structure_bsp", "pathfinding_edges"): "byte",
    # the paired visibility views have identical layouts; bind the readers'
    ("structure_bsp", "surface_references"): "structure_surface_reference",
    ("structure_bsp", "cluster_portals"): "structure_cluster_portal",
    ("structure_bsp", "fog_planes"): "structure_fog_plane_render",
    ("structure_lightmap", "materials"): "structure_material",
    ("game_globals", "materials"): "damage_resistance_material",
    # the cluster's portal list is a block of shorts; the surface lists are
    # blocks of longs (all read through the bare C types)
    ("structure_cluster", "portal_indices"): "short",
    ("structure_cluster", "surface_indices"): "long",
    ("structure_visibility_subcluster", "surface_indices"): "long",
    # the animation graph's own animations are `struct animation`; the
    # seats'/weapon classes' same-named blocks are index lists
    # (model_animation_definitions.h's comments say so)
    ("animation_graph", "animations"): "animation",
    ("animation_graph_unit_seat", "animations"): "animation_graph_animation_index",
    ("animation_graph_weapon_class", "animations"): "animation_graph_animation_index",
    ("animation_graph_weapon_type", "animations"): "animation_graph_animation_index",
    ("animation_graph_weapon_animations", "animations"): "animation_graph_animation_index",
    ("animation_graph_first_person_weapon_animations", "animations"): "animation_graph_animation_index",
    ("animation_graph_device_animations", "animations"): "animation_graph_animation_index",
    ("vehicle_animation", "animations"): "animation_graph_animation_index",
    # the shader maps: the call sites use both the chicago and the generic
    # map structs against either block, so bind them by hand
    ("shader_transparent_chicago_definition", "maps"): "shader_transparent_chicago_map",
    ("chicago", "maps"): "shader_transparent_chicago_map",
    ("shader_transparent_generic_definition", "maps"): "shader_transparent_generic_map",
    ("generic", "maps"): "shader_transparent_generic_map",
    ("generic", "stages"): "shader_transparent_generic_stage",
}

# blocks of a scalar type (not a struct): "short", ... — element sizes as
# (file, LP64 memory, signed); `long` widens like everywhere else
SCALAR_ELEMENTS = {
    "byte": (1, 1, False),
    "char": (1, 1, False),
    "short": (2, 2, True),
    "word": (2, 2, False),
    "real": (4, 4, False),
    "long": (4, 8, True),
}

# element structures the decompilation never defines: the object placements
# share the object datum + permutation composite, as scenery_place writes it
COMPOSITE_ELEMENTS = {
    "scenario_scenery_datum": ["scenario_object_datum", "scenario_object_permutation"],
    "scenario_sound_scenery_datum": ["scenario_object_datum", "scenario_object_permutation"],
}

# tag_data fields whose bytes are a data_array of the given structure
# ("a blob with structure", docs/linux64.md)
DATA_ARRAY_OVERRIDES = {
    ("scenario", "hs_syntax_data"): "hs_syntax_node",
}

SPECIAL_STRUCTS = {"tag_block": "block", "tag_reference": "reference", "tag_data": "data"}


class Type:
    def __init__(self, kind, name=None, size=0, signed=False, element=None, count=None,
                 plain=False, die=None):
        self.kind = kind  # base | pointer | array | struct | union | enum | void
        self.name = name
        self.size = size
        self.signed = signed
        self.element = element
        self.count = count
        # struct/union: every field keeps its offset and size between the two
        # builds (no pointers, no longs anywhere inside) — bulk-copyable
        self.plain = plain
        self.die = die


class Member:
    def __init__(self, name, offset, type_):
        self.name = name      # None for anonymous members
        self.offset = offset
        self.type = type_


# base types that change width between the 32-bit and LP64 builds (clang's
# DWARF calls them "long", not "long int")
def _is_wide_type(die):
    nm = die.attributes.get("DW_AT_name")
    if not nm:
        return False
    return nm.value.decode("utf-8", "surrogateescape") in (
        "long", "unsigned long", "long int", "long unsigned int",
        "long long", "unsigned long long", "long long int", "long long unsigned int")


class DwarfStructs:
    """struct name -> {"size", "members": [Member], "is_union"} for one binary"""

    def __init__(self, path):
        self.dwarf = None
        self.structs = {}
        self.conflicts = []
        # (struct, member, kept offset, dropped offset): a member two
        # per-unit views place at different offsets. Harmless on the 32-bit
        # build (the asserts pin the disk offsets), a mistranslation on LP64:
        # the map keeps one offset while the other view's unit reads the
        # other. Each entry is a struct to define once (docs/linux64.md).
        self.member_conflicts = []
        self._plain_cache = {}
        with open(path, "rb") as f:
            self.dwarf = ELFFile(f).get_dwarf_info()
            for cu in self.dwarf.iter_CUs():
                self._walk(cu.get_top_DIE())

    def _walk(self, die):
        if die.tag in ("DW_TAG_structure_type", "DW_TAG_union_type"):
            a = die.attributes
            if a.get("DW_AT_name") and a.get("DW_AT_byte_size") is not None:
                name = a["DW_AT_name"].value.decode("utf-8", "surrogateescape")
                members = []
                for child in die.iter_children():
                    if child.tag == "DW_TAG_member":
                        m = child.attributes
                        loc = m.get("DW_AT_data_member_location")
                        members.append(Member(
                            m["DW_AT_name"].value.decode("utf-8", "surrogateescape") if m.get("DW_AT_name") else None,
                            loc.value if loc else 0,
                            self._resolve(child, m.get("DW_AT_type"))))
                signature = repr([(m.name, m.offset, m.type and (m.type.kind, m.type.name, m.type.size))
                                  for m in members]) + str(a["DW_AT_byte_size"].value)
                old = self.structs.get(name)
                if old is None:
                    self.structs[name] = {"size": a["DW_AT_byte_size"].value, "members": members,
                                          "is_union": die.tag == "DW_TAG_union_type",
                                          "signature": signature}
                elif old["signature"] != signature:
                    # the decompilation splits some structures into partial
                    # per-unit definitions (e.g. struct sky): the disk format
                    # is their union. Keep the richest, then merge the other
                    # variants' members (each keeps its own offset; names
                    # already present are dropped: same bytes).
                    self.conflicts.append(name)
                    by_name = {m.name: m.offset for m in old["members"] if m.name}
                    for m in members:
                        if m.name and m.name in by_name and by_name[m.name] != m.offset:
                            self.member_conflicts.append((name, m.name, by_name[m.name], m.offset))
                    if len(members) > len(old["members"]):
                        have = {m.name for m in members}
                        self.structs[name] = {"size": max(a["DW_AT_byte_size"].value, old["size"]),
                                              "members": members + [m for m in old["members"]
                                                                    if m.name not in have],
                                              "is_union": die.tag == "DW_TAG_union_type",
                                              "signature": signature}
                    else:
                        have = {m.name for m in old["members"]}
                        self.structs[name]["members"] = old["members"] + \
                            [m for m in members if m.name not in have]
                        self.structs[name]["size"] = max(self.structs[name]["size"],
                                                         a["DW_AT_byte_size"].value)
        for child in die.iter_children():
            if child.tag != "DW_TAG_member":
                self._walk(child)

    def _is_plain(self, die, cache=None, depth=0):
        """layout-invariant across the two builds: no pointers and no
        `long`-family members anywhere inside (those widen on LP64)"""
        if cache is None:
            cache = self._plain_cache
        if die.offset in cache:
            return cache[die.offset]
        if depth > 32:
            return False
        cache[die.offset] = False  # recursion guard (a pointer cycle is not plain anyway)
        plain = True
        for child in die.iter_children():
            if child.tag != "DW_TAG_member":
                continue
            tdie = self._die_of(child, child.attributes.get("DW_AT_type"))
            while tdie is not None and tdie.tag in ("DW_TAG_typedef", "DW_TAG_const_type",
                                                    "DW_TAG_volatile_type", "DW_TAG_restrict_type"):
                tdie = self._die_of(tdie, tdie.attributes.get("DW_AT_type"))
            if tdie is None:
                continue
            if tdie.tag == "DW_TAG_pointer_type":
                plain = False
                break
            if tdie.tag == "DW_TAG_base_type":
                if _is_wide_type(tdie):
                    plain = False
                    break
                continue
            if tdie.tag in ("DW_TAG_structure_type", "DW_TAG_union_type"):
                plain = self._is_plain(tdie, cache, depth + 1)
                if not plain:
                    break
                continue
            if tdie.tag == "DW_TAG_array_type":
                edie = self._die_of(tdie, tdie.attributes.get("DW_AT_type"))
                while edie is not None and edie.tag in ("DW_TAG_typedef", "DW_TAG_const_type",
                                                        "DW_TAG_volatile_type", "DW_TAG_restrict_type"):
                    edie = self._die_of(edie, edie.attributes.get("DW_AT_type"))
                if edie is not None and edie.tag == "DW_TAG_pointer_type":
                    plain = False
                    break
                if edie is not None and edie.tag in ("DW_TAG_structure_type", "DW_TAG_union_type"):
                    plain = self._is_plain(edie, cache, depth + 1)
                    if not plain:
                        break
                if edie is not None and edie.tag == "DW_TAG_base_type":
                    if _is_wide_type(edie):
                        plain = False
                        break
        cache[die.offset] = plain
        return plain

    def _die_of(self, owner, attr):
        """DW_AT_type reference: CU-relative for refN forms, absolute for ref_addr"""
        if attr is None:
            return None
        if attr.form == "DW_FORM_ref_addr":
            offset = attr.value
        else:
            offset = owner.cu.cu_offset + attr.value
        return self.dwarf.get_DIE_from_refaddr(offset)

    def _resolve(self, owner, attr):
        if attr is None:
            return Type("void")
        die = self._die_of(owner, attr)
        while die and die.tag == "DW_TAG_typedef":
            attr = die.attributes.get("DW_AT_type")
            die = self._die_of(die, attr) if attr is not None else None
        if die is None:
            return Type("void")
        a = die.attributes
        if die.tag == "DW_TAG_base_type":
            enc = a.get("DW_AT_encoding")
            signed = enc is not None and enc.value in (5, 7)  # DW_ATE_signed, DW_ATE_signed_char
            nm = a["DW_AT_name"].value if "DW_AT_name" in a else b"?"
            return Type("base", nm.decode("utf-8", "surrogateescape"),
                        a["DW_AT_byte_size"].value if "DW_AT_byte_size" in a else 4, signed)
        if die.tag == "DW_TAG_pointer_type":
            return Type("pointer", None, a["DW_AT_byte_size"].value if "DW_AT_byte_size" in a else 4)
        if die.tag == "DW_TAG_enumeration_type":
            nm = a["DW_AT_name"].value if "DW_AT_name" in a else b"?"
            return Type("enum", nm.decode("utf-8", "surrogateescape"),
                        a["DW_AT_byte_size"].value if "DW_AT_byte_size" in a else 4, True)
        if die.tag == "DW_TAG_array_type":
            elem = self._resolve(die, a.get("DW_AT_type"))
            count = None
            for sub in die.iter_children():
                if sub.tag == "DW_TAG_subrange_type":
                    # clang emits DW_AT_count; gcc DW_AT_upper_bound
                    if "DW_AT_count" in sub.attributes:
                        count = sub.attributes["DW_AT_count"].value
                    elif "DW_AT_upper_bound" in sub.attributes:
                        count = sub.attributes["DW_AT_upper_bound"].value + 1
            size = a["DW_AT_byte_size"].value if "DW_AT_byte_size" in a else 0
            if not size and count and elem.size:
                size = count * elem.size
            if count is None and elem.size and size:
                count = size // elem.size
            return Type("array", None, size, element=elem, count=count)
        if die.tag in ("DW_TAG_structure_type", "DW_TAG_union_type"):
            nm = a["DW_AT_name"].value if "DW_AT_name" in a else b""
            return Type("struct" if die.tag == "DW_TAG_structure_type" else "union",
                        nm.decode("utf-8", "surrogateescape"),
                        a["DW_AT_byte_size"].value if "DW_AT_byte_size" in a else 0,
                        plain=self._is_plain(die), die=die)
        if die.tag in ("DW_TAG_const_type", "DW_TAG_volatile_type", "DW_TAG_restrict_type"):
            return self._resolve(die, a.get("DW_AT_type"))
        return Type("base", die.tag, a.get("DW_AT_byte_size", 0))


type32default = 4  # fallback byte size


PADDING_NAME = re.compile(
    r"^(unknown|unused|pad|reserved|padding|sad_unused|lonely_unused|"
    r"rapidly_dwindling_unused_space|diminishing_misc_unused|scripting_unused|"
    r"user_edit_unused|header_unused|reference_unused|cluster_unused|fog_unused|"
    r"weather_unused|sound_unused|render_unused|misc_unused|editor_scenario_unused|"
    r"unused_blocks|sad|lonely|editor|misc)")

class Field:
    def __init__(self, name, kind, off32, size32, off64, size64):
        self.name = name
        self.kind = kind  # scalar | pointer | block | reference | data
        self.signed = False
        self.off32, self.size32 = off32, size32
        self.off64, self.size64 = off64, size64
        self.element = None  # block element struct name
        self.padding = False  # a padding array (a partial definition's filler)


class Generator:
    def __init__(self, structs32, structs64):
        self.s32 = structs32
        self.s64 = structs64
        self.comments = {}
        self.callsites = {}
        self.errors = []
        self.warnings = []
        self.tables = {}   # struct name -> [Field]
        self.groups_of = defaultdict(list)  # struct name -> [fourcc, ...] (roots only)
        self.scalar_blocks = set()  # scalar element types used by blocks
        self.composite_sizes = {}  # composite name -> (file size, mem size)
        self.sizes = {}  # struct name -> (file size, mem size), covering all fields

    # ---- field flattening -------------------------------------------------

    def members64_by_name(self, name):
        s = self.s64.structs.get(name)
        if not s:
            return {}
        return {m.name: m for m in s["members"] if m.name}

    def flatten(self, name):
        """leaf fields of struct `name`, both layouts"""
        s32 = self.s32.structs.get(name)
        s64 = self.s64.structs.get(name)
        if not s32 or not s64:
            self.errors.append(f"struct {name}: no DWARF in {'32-bit' if not s32 else '64-bit'} build")
            return []
        out = []
        m64 = self.members64_by_name(name)
        anon64 = [m for m in s64["members"] if m.name is None] if s64 else []
        anon_index = 0
        for mem in s32["members"]:
            if mem.name is None:
                # anonymous struct/union member (MSVC extension)
                if mem.type.plain and mem.type.size:
                    out.append(Field(f"{name}.anon", "scalar", mem.offset, mem.type.size,
                                     mem.offset, mem.type.size))
                    anon_index += 1
                    continue
                peer64 = anon64[anon_index] if anon_index < len(anon64) else None
                anon_index += 1
                inner = self.emit_anonym(mem.type, peer64.type if peer64 else None,
                                         mem.offset, peer64.offset if peer64 else mem.offset,
                                         f"{name}.")
                out.extend(inner)
                continue
            peer = m64.get(mem.name)
            if peer is None:
                self.errors.append(f"{name}.{mem.name}: missing in the 64-bit struct")
                continue
            out.extend(self.emit_field(f"{name}.{mem.name}", mem.type, peer.type,
                                       mem.offset, peer.offset))
        return out

    def emit_anonym(self, t32, t64, off32, off64, prefix):
        """an anonymous struct/union member: the two sides pair by position;
        unions take the first alternative"""
        out = []
        if t32.kind == "union":
            # the first alternative is as good as any: same bytes
            for die32, die64 in ((t32.die, t64.die if t64 else None),):
                m32 = next((c for c in die32.iter_children() if c.tag == "DW_TAG_member"), None) if die32 else None
                m64 = next((c for c in die64.iter_children() if c.tag == "DW_TAG_member"), None) if die64 else None
                if m32 is not None and m64 is not None:
                    mt32 = self.s32._resolve(m32, m32.attributes.get("DW_AT_type"))
                    mt64 = self.s64._resolve(m64, m64.attributes.get("DW_AT_type"))
                    out.extend(self.emit_field(prefix + "anon", mt32, mt64, off32, off64))
            return out
        if t32.kind == "struct":
            # recurse members pairwise (document order is the same source)
            mems32 = [m for m in t32.die.iter_children() if m.tag == "DW_TAG_member"] if t32.die else []
            mems64 = [m for m in t64.die.iter_children() if m.tag == "DW_TAG_member"] if t64 and t64.die else []
            for i, m32 in enumerate(mems32):
                if i >= len(mems64):
                    break
                m64 = mems64[i]
                mt32 = self.s32._resolve(m32, m32.attributes.get("DW_AT_type"))
                mt64 = self.s64._resolve(m64, m64.attributes.get("DW_AT_type"))
                mo32 = m32.attributes.get("DW_AT_data_member_location")
                mo64 = m64.attributes.get("DW_AT_data_member_location")
                out.extend(self.emit_field(prefix + "anon", mt32, mt64,
                                           off32 + (mo32.value if mo32 else 0),
                                           off64 + (mo64.value if mo64 else 0)))
            return out
        return out

    def emit_field(self, path, t32, t64, off32, off64):
        out = []
        if t32.kind == "struct" and t32.name in SPECIAL_STRUCTS:
            out.append(Field(path, SPECIAL_STRUCTS[t32.name], off32, t32.size, off64, t64.size))
            return out
        if t32.kind == "pointer":
            out.append(Field(path, "pointer", off32, 4, off64, 8))
            return out
        if t32.kind in ("base", "enum"):
            f = Field(path, "scalar", off32, t32.size, off64, t64.size)
            f.signed = t32.signed
            out.append(f)
            return out
        if t32.kind == "array":
            return self.emit_array(path, t32, t64, off32, off64)
        if t32.kind == "struct":
            if t32.plain and t64.plain and t32.size and t32.size == t64.size:
                return [Field(path, "scalar", off32, t32.size, off64, t64.size)]
            out.extend(self.flatten_nested(path, t32.name, off32, off64))
            return out
        if t32.kind == "union":
            if t32.plain and t64.plain and t32.size and t32.size == t64.size:
                return [Field(path, "scalar", off32, t32.size, off64, t64.size)]
            # first alternative only; all alternatives share the bytes
            s32 = self.s32.structs.get(t32.name)
            if s32 and s32["members"]:
                m = s32["members"][0]
                p64 = self.members64_by_name(t32.name).get(m.name)
                if p64 is not None:
                    out.extend(self.emit_field(path, m.type, p64.type, off32 + m.offset, off64 + p64.offset))
            return out
        if t32.kind == "void":
            self.warnings.append(f"{path}: unresolved type; assuming 4-byte scalar")
            out.append(Field(path, "scalar", off32, 4, off64, 4))
            return out
        self.errors.append(f"{path}: unhandled type {t32.kind}")
        return out

    def emit_array(self, path, t32, t64, off32, off64):
        e32, e64 = t32.element, t64.element
        count = t32.count or 0
        if e32.kind in ("base", "enum") and e32.size == e64.size:
            f = Field(path, "scalar", off32, t32.size, off64, t64.size)
            f.padding = bool(PADDING_NAME.match(path.split(".")[-1])) and e32.size == 1
            return [f]
        if e32.kind in ("struct", "union") and e32.plain and e64.plain and e32.size == e64.size:
            f = Field(path, "scalar", off32, t32.size, off64, t64.size)
            f.padding = bool(PADDING_NAME.match(path.split(".")[-1]))
            return [f]
        if count and count <= 512 and e32.size and e64.size:
            out = []
            for i in range(count):
                o32 = off32 + i * e32.size
                o64 = off64 + i * e64.size
                out.extend(self.emit_field(f"{path}[{i}]", e32, e64, o32, o64))
            return out
        # huge or unknown count: raw copy of the smaller size (padding differs)
        self.warnings.append(f"{path}: array of {count} x {e32.kind} {e32.name or ''}; copied raw")
        return [Field(path, "scalar", off32, min(t32.size, t64.size), off64, min(t32.size, t64.size))]

    def flatten_nested(self, path, name, off32, off64):
        if name in SPECIAL_STRUCTS:
            s32, s64 = self.s32.structs[name], self.s64.structs[name]
            return [Field(path, SPECIAL_STRUCTS[name], off32, s32["size"], off64, s64["size"])]
        s32 = self.s32.structs.get(name)
        s64 = self.s64.structs.get(name)
        if not s32 or not s64:
            self.errors.append(f"{path}: nested struct {name} has no DWARF")
            return []
        out = []
        m64 = self.members64_by_name(name)
        anon64 = [m for m in s64["members"] if m.name is None]
        anon_index = 0
        for mem in s32["members"]:
            if mem.name is None:
                if mem.type.kind in ("struct", "union"):
                    if mem.type.plain and mem.type.size:
                        out.append(Field(path + ".anon", "scalar", off32 + mem.offset,
                                         mem.type.size, off64 + mem.offset, mem.type.size))
                        anon_index += 1
                    else:
                        peer64 = anon64[anon_index] if anon_index < len(anon64) else None
                        anon_index += 1
                        out.extend(self.emit_anonym(mem.type, peer64.type if peer64 else None,
                                                    off32 + mem.offset,
                                                    off64 + (peer64.offset if peer64 else mem.offset),
                                                    path + "."))
                continue
            peer = m64.get(mem.name)
            if peer is None:
                continue
            out.extend(self.emit_field(f"{path}.{mem.name}", mem.type, peer.type,
                                       off32 + mem.offset, off64 + peer.offset))
        return out

    def _flatten_composite(self, name, todo, done):
        """a synthetic map for an element the decompiler never wrote as one
        struct: its members, concatenated (COMPOSITE_ELEMENTS)"""
        if name in self.tables:
            return
        fields = []
        off32 = 0
        off64 = 0
        for member in COMPOSITE_ELEMENTS[name]:
            mfields = self.flatten(member)
            if not self.s32.structs.get(member) or not self.s64.structs.get(member):
                self.errors.append(f"composite {name}: member {member} missing")
                continue
            for f in mfields:
                f.off32 += off32
                f.off64 += off64
            fields.extend(mfields)
            off32 += self.s32.structs[member]["size"]
            off64 += self.s64.structs[member]["size"]
            for f in mfields:
                if f.kind == "block" and f.element and f.element not in done:
                    todo.append((None, f.element))
        self.tables[name] = fields
        self.composite_sizes[name] = (off32, off64)

    # ---- the walk ---------------------------------------------------------

    def run(self):
        todo = [(group, root) for group, root in GROUP_ROOTS.items()]
        done = set()
        while todo:
            group, root = todo.pop()
            if group:  # several groups can share a root structure
                self.groups_of.setdefault(root, []).append(group)
            if root in done:
                continue
            done.add(root)
            fields = self.flatten(root)
            # merged partial definitions overlap: a padding array from one
            # can cover another's real fields; the real fields win
            specialized = [f for f in fields if not f.padding]
            dropped = 0
            for f in list(fields):
                if not f.padding:
                    continue
                for o in specialized:
                    if f.off32 < o.off32 + o.size32 and o.off32 < f.off32 + f.size32:
                        fields.remove(f)
                        dropped += 1
                        break
            for f in fields:
                if f.padding and f.size32 > 4:
                    self.warnings.append(f"{root}: dropping overlapping padding {f.name}")
            if dropped:
                self.warnings.append(
                    f"{root}: merged partial definitions; dropped {dropped} overlapping padding fields")
            for f in fields:
                leaf = re.sub(r"\[\d+\]$", "", f.name.split(".")[-1])
                parent = f.name.split(".")[-2] if "." in f.name else root
                if f.kind == "data":
                    # a data blob holding a data array of structures
                    data_override = (DATA_ARRAY_OVERRIDES.get((parent, leaf)) or
                                     DATA_ARRAY_OVERRIDES.get((root, leaf)) or
                                     DATA_ARRAY_OVERRIDES.get(leaf))
                    if data_override:
                        f.kind = "data_array"
                        f.element = data_override
                        for extra in ("data_array", data_override):
                            if extra not in done:
                                todo.append((None, extra))
                    continue
                if f.kind != "block":
                    continue
                override = (BLOCK_OVERRIDES.get((parent, leaf)) or BLOCK_OVERRIDES.get((root, leaf))
                            or BLOCK_OVERRIDES.get(leaf))
                # header comments beat call-site mining
                candidates = self.comments.get(leaf) or self.callsites.get(leaf, set())
                if override:
                    f.element = override
                elif len(candidates) == 1:
                    f.element = next(iter(candidates))
                else:
                    # not an error: a block with count 0 on disk needs no
                    # element layout. The runtime logs loudly if it meets a
                    # non-empty one (docs/linux64.md).
                    self.warnings.append(
                        f"{f.name}: block element unknown "
                        f"(candidates: {', '.join(sorted(candidates)) or 'none'})")
                    continue
                if f.element in SCALAR_ELEMENTS:
                    self.scalar_blocks.add(f.element)
                    continue
                if f.element in COMPOSITE_ELEMENTS:
                    self._flatten_composite(f.element, todo, done)
                    continue
                if f.element not in done:
                    todo.append((None, f.element))
            self.tables[root] = fields
            # a merged partial view can declare a sizeof smaller than the
            # fields it contributes (the tail is another view's): the map's
            # sizes must cover every field, or the arena allocation under-
            # allocates and the translator writes past it
            if root in self.s32.structs and root in self.s64.structs:
                cover32 = max((f.off32 + f.size32) for f in fields) if fields else 0
                cover64 = max((f.off64 + f.size64) for f in fields) if fields else 0
                self.sizes[root] = (max(self.s32.structs[root]["size"], cover32),
                                    max(self.s64.structs[root]["size"], cover64))
        return not self.errors

    # ---- emission ---------------------------------------------------------

    def emit(self):
        def sym(name):
            return re.sub(r"\W", "_", name)

        out = ["/* generated by tools/linux64_layout.py; do not edit (docs/linux64.md) */",
               "#ifdef HALO_LINUX64", "", '#include "tag_translate64.h"', "",
               "/* blocks of a scalar type (a block of shorts, say) */"]
        for scalar in sorted(self.scalar_blocks):
            file_size, mem_size, signed = SCALAR_ELEMENTS[scalar]
            kind = "F64_SCALAR_SIGNED" if signed else "F64_SCALAR_UNSIGNED"
            out.append(f"static const struct field_map64 fields_scalar_{sym(scalar)}[] = {{")
            out.append(f"\t{{ 0x0, {file_size}, 0x0, {mem_size}, {kind}, NULL, NULL }},")
            out.append("};")
            out.append(f"static const struct struct_map64 map_scalar_{sym(scalar)} = "
                       f"{{ \"{scalar}\", 0x{file_size:X}, 0x{mem_size:X}, 1, fields_scalar_{sym(scalar)} }};")
            out.append("")
        out.append("/* the maps reference each other */")
        for name in sorted(self.tables):
            out.append(f"static const struct struct_map64 map_{sym(name)};")
        out.append("")
        for name in sorted(self.tables):
            s = sym(name)
            out.append(f"static const struct field_map64 fields_{s}[] = {{")
            for f in self.tables[name]:
                sub = (f"&map_{sym(f.element)}" if f.element and f.element not in SCALAR_ELEMENTS
                       else f"&map_scalar_{sym(f.element)}" if f.element else "NULL")
                kind = {"scalar": "F64_SCALAR_UNSIGNED" if not f.signed else "F64_SCALAR_SIGNED",
                        "pointer": "F64_POINTER", "block": "F64_BLOCK",
                        "reference": "F64_REFERENCE", "data": "F64_DATA",
                        "data_array": "F64_DATA_ARRAY"}[f.kind]
                out.append(f"\t{{ 0x{f.off32:X}, {f.size32}, 0x{f.off64:X}, {f.size64}, {kind}, {sub}, \"{f.name}\" }},"
                           )
            out.append("};")
            sizes = (self.composite_sizes.get(name) or self.sizes.get(name) or
                     (self.s32.structs[name]["size"], self.s64.structs[name]["size"]))
            out.append(f"static const struct struct_map64 map_{s} = {{ \"{name}\", "
                       f"0x{sizes[0]:X}, 0x{sizes[1]:X}, "
                       f"{len(self.tables[name])}, fields_{s} }};")
            out.append("")
        out.append("const struct struct_map64 *tag_group_layout_64(unsigned long group_tag)")
        out.append("{")
        out.append("\tswitch (group_tag)")
        out.append("\t{")
        for name, groups in sorted(self.groups_of.items()):
            for group in groups:
                out.append(f"\tcase '{group}': return &map_{sym(name)};")
        out.append("\tdefault: return NULL;")
        out.append("\t}")
        out.append("}")
        out.append("")
        if "data_array" in self.tables:
            out.append("/* the data_array header's own layout, for F64_DATA_ARRAY blobs */")
            out.append("const struct struct_map64 *tag_helper_data_array_64(void)")
            out.append("{")
            out.append("\treturn &map_data_array;")
            out.append("}")
            out.append("")
        out.append("#endif /* HALO_LINUX64 */")
        OUTPUT.write_text("\n".join(out) + "\n")


def mine_block_bindings():
    """block field -> element structure:
    - comments: the decompiler's `struct tag_block name; // element_type`
      annotations in the definition headers (first class),
    - callsites: TAG_BLOCK_GET_ELEMENT(&x->field, index, struct element)
      (second class: regex mining misfires in a few macro nests)"""
    comments = defaultdict(set)
    callsites = defaultdict(set)
    decl = re.compile(r"struct tag_block\s+(\w+)(\[\d+\])?\s*;\s*//\s*(\w+)\s*$")
    for p in Path("source").rglob("*.h"):
        for line in p.read_text(errors="surrogateescape").split("\n"):
            m = decl.search(line)
            if m:
                comments[m.group(1)].add(m.group(3))

    pat = re.compile(r"TAG_BLOCK_(?:TRY_AND_)?GET_ELEMENT\(\s*(.*?),\s*(.*?),\s*struct\s+(\w+)\s*\)", re.DOTALL)
    for p in Path("source").rglob("*.c"):
        text = p.read_text(errors="surrogateescape")
        for m in pat.finditer(text):
            expr, ty = m.group(1).strip(), m.group(3)
            # reject matches that leap across statements or macro boundaries
            if len(expr) > 80 or any(c in expr for c in ";{}?\\"):
                continue
            fm = re.search(r"[>.](\w+)$", expr) or re.match(r"&?(\w+)$", expr)
            if fm:
                callsites[fm.group(1)].add(ty)
    return comments, callsites


def main():
    print(f"reading {BUILD32} ...", file=sys.stderr)
    s32 = DwarfStructs(BUILD32)
    print(f"  {len(s32.structs)} structs", file=sys.stderr)
    print(f"reading {BUILD64} ...", file=sys.stderr)
    s64 = DwarfStructs(BUILD64)
    print(f"  {len(s64.structs)} structs", file=sys.stderr)
    comments, callsites = mine_block_bindings()
    print(f"  {len(comments)} comment bindings, {len(callsites)} call-site bindings", file=sys.stderr)

    if s32.member_conflicts:
        print("note: the 32-bit build has inconsistent views (unexpected!):", file=sys.stderr)
        for name, member, kept, dropped in s32.member_conflicts:
            print(f"  {name}.{member}: 0x{kept:X} vs 0x{dropped:X}", file=sys.stderr)
    if s64.member_conflicts:
        print("LP64 view conflicts (the map keeps one offset; the other unit "
              "misreads — define the struct once, docs/linux64.md):", file=sys.stderr)
        seen = set()
        for name, member, kept, dropped in s64.member_conflicts:
            if (name, member) in seen:
                continue
            seen.add((name, member))
            print(f"  {name}.{member}: 0x{kept:X} vs 0x{dropped:X}", file=sys.stderr)

    gen = Generator(s32, s64)
    gen.comments = comments
    gen.callsites = callsites
    ok = gen.run()
    for w in gen.warnings:
        print("warning:", w, file=sys.stderr)
    for e in gen.errors:
        print("ERROR:", e, file=sys.stderr)
    if not ok:
        print(f"{len(gen.errors)} problems; table NOT written", file=sys.stderr)
        sys.exit(1)
    gen.emit()
    print(f"wrote {OUTPUT}: {len(gen.tables)} structs", file=sys.stderr)


if __name__ == "__main__":
    main()
