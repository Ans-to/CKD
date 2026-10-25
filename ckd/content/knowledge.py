"""Curated bilingual explanations ("knowledge packs").

Each pack is a hand-written, reviewable explanation of one topic family in
English and Urdu, together with the visual world it belongs to and the *actions*
the visual builder should play while each clause is narrated.

Why hand-written packs instead of only an LLM?
  * The pipeline must work with zero model downloads (free Colab, CPU only).
  * Explanations are the part where being wrong is worst; a small curated set of
    vetted packs gives high quality for common topics, and the generic composer
    (or an optional local LLM) covers everything else, clearly labelled.

Packs are data, not code: add a new topic by appending a dict to PACKS.
Every scene lists `narration` for both languages (semantically aligned clauses),
`actions` (per clause) chosen from the world's action vocabulary, and `elements`.

Facts policy: only widely established explanations are used. Numbers are
qualified ("about", "typical") and time-sensitive claims are avoided. No
citations are invented; packs recorded no web research.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

PACKS: List[Dict[str, Any]] = []


def _pack(**kw) -> Dict[str, Any]:
    PACKS.append(kw)
    return kw


# ===========================================================================
# SOLAR ENERGY
# ===========================================================================
_pack(
    id="solar",
    world="solar",
    palette="warm",
    match=[
        "solar", "solar panel", "solar energy", "photovoltaic", "pv panel", "sunlight electricity",
        "سولر", "شمسی", "سورج", "سولر انرجی", "شمسی توانائی",
    ],
    title={"en": "How Solar Panels Make Electricity", "ur": "سولر پینل بجلی کیسے بناتے ہیں"},
    keywords={"en": ["solar panels", "photons", "silicon", "inverter", "battery"],
              "ur": ["سولر پینل", "روشنی", "سلکان", "انورٹر", "بیٹری"]},
    scenes=[
        {
            "id": "hook",
            "purpose": "hook",
            "headline": {"en": "Sunlight is already on your roof",
                         "ur": "دھوپ پہلے سے آپ کی چھت پر ہے"},
            "narration": {
                "en": "Every day, sunlight lands on your roof. Most of it turns into heat and drifts away. A solar panel catches that light and turns part of it into electricity.",
                "ur": "ہر روز سورج کی روشنی آپ کی چھت پر پڑتی ہے۔ اس کا زیادہ تر حصہ گرمی بن کر اڑ جاتا ہے۔ سولر پینل اس روشنی کو پکڑ کر اس کا کچھ حصہ بجلی میں بدل دیتا ہے۔",
            },
            "elements": [
                {"type": "sky", "slot": "back"},
                {"type": "sun", "slot": "sun"},
                {"type": "house", "slot": "house"},
                {"type": "panel", "slot": "roof", "params": {"rows": 3, "cols": 4}},
                {"type": "label", "slot": "panel_label",
                 "params": {"en": "solar panel", "ur": "سولر پینل"}},
            ],
            "actions": [
                {"action": "sun_rise", "params": {}},
                {"action": "rays_travel", "params": {"count": 9}},
                {"action": "panel_glow", "params": {}},
            ],
            "character": {"pose": "point_right", "slot": "char_left"},
        },
        {
            "id": "cells",
            "purpose": "explain",
            "headline": {"en": "Inside: silicon cells", "ur": "اندر کیا ہے؟ سلکان کے خلیے"},
            "narration": {
                "en": "Inside the panel sit many silicon cells. When light particles, called photons, hit the silicon, they knock electrons loose. Those electrons flow, and flowing electrons are an electric current.",
                "ur": "پینل کے اندر سلکان کے بہت سے خلیے ہوتے ہیں۔ جب روشنی کے ذرے، جنہیں فوٹون کہتے ہیں، سلکان پر گرتے ہیں تو وہ الیکٹرانوں کو آزاد کر دیتے ہیں۔ یہ الیکٹران بہنے لگتے ہیں، اور بہتے الیکٹران ہی برقی رو کہلاتے ہیں۔",
            },
            "elements": [
                {"type": "sky", "slot": "back"},
                {"type": "sun", "slot": "sun"},
                {"type": "layer_stack", "slot": "stack",
                 "params": {"labels_en": ["glass", "silicon cell", "backing"],
                            "labels_ur": ["شیشہ", "سلکان خلیہ", "پچھلی تہہ"]}},
            ],
            "actions": [
                {"action": "explode_layers", "params": {}},
                {"action": "photons_hit", "params": {"count": 16}},
                {"action": "electrons_flow", "params": {}},
            ],
            "character": {"pose": "think", "slot": "char_left"},
        },
        {
            "id": "inverter",
            "purpose": "explain",
            "headline": {"en": "DC becomes AC", "ur": "ڈی سی بنتی ہے اے سی"},
            "narration": {
                "en": "The panel produces direct current, which always flows one way. Your home needs alternating current that changes direction many times a second. An inverter makes that change.",
                "ur": "پینل ڈائریکٹ کرنٹ بناتا ہے، جو ہمیشہ ایک ہی سمت میں بہتا ہے۔ آپ کے گھر کو متبادل کرنٹ چاہیے جو ہر سیکنڈ کئی بار سمت بدلتا ہے۔ انورٹر یہ تبدیلی کرتا ہے۔",
            },
            "elements": [
                {"type": "panel", "slot": "stage_left", "params": {"rows": 3, "cols": 3}},
                {"type": "inverter", "slot": "stage_right"},
                {"type": "wire", "slot": "wire", "params": {"from": "panel", "to": "inverter"}},
            ],
            "actions": [
                {"action": "dc_arrow", "params": {}},
                {"action": "inverter_pulse", "params": {}},
                {"action": "ac_wave", "params": {}},
            ],
            "character": {"pose": "present", "slot": "char_left"},
        },
        {
            "id": "storage",
            "purpose": "explain",
            "headline": {"en": "Store it or share it", "ur": "ذخیرہ کریں یا بانٹیں"},
            "narration": {
                "en": "Power you do not use right away is either stored in a battery or sent into the grid. That way the lights still work after sunset.",
                "ur": "جو بجلی آپ فوراً استعمال نہیں کرتے، وہ بیٹری میں محفوظ ہو جاتی ہے یا گرڈ میں چلی جاتی ہے۔ اسی طرح سورج ڈوبنے کے بعد بھی بتیاں جلی رہتی ہیں۔",
            },
            "elements": [
                {"type": "panel", "slot": "stage_left", "params": {"rows": 3, "cols": 3}},
                {"type": "battery", "slot": "stage_right"},
                {"type": "grid", "slot": "grid"},
                {"type": "wire", "slot": "wire", "params": {"from": "panel", "to": "battery"}},
            ],
            "actions": [
                {"action": "split_flow", "params": {}},
                {"action": "battery_fill", "params": {}},
                {"action": "night_glow", "params": {}},
            ],
            "character": {"pose": "point_right", "slot": "char_left"},
        },
        {
            "id": "limits",
            "purpose": "example",
            "headline": {"en": "About one fifth becomes power", "ur": "تقریباً پانچواں حصہ بجلی بنتا ہے"},
            "narration": {
                "en": "A typical panel turns roughly one fifth of the sunlight hitting it into electricity; the rest becomes heat. More panels, and a clear view of the sky, give you more power.",
                "ur": "عام طور پر ایک پینل پر پڑنے والی روشنی کا تقریباً پانچواں حصہ بجلی بنتا ہے، باقی گرمی بن جاتا ہے۔ زیادہ پینل اور کھلا آسمان زیادہ بجلی دیتے ہیں۔",
            },
            "elements": [
                {"type": "efficiency_bar", "slot": "stage", "params": {"share": 0.2}},
                {"type": "heat_arrows", "slot": "stage", "params": {}},
                {"type": "array", "slot": "stage_right", "params": {"rows": 2, "cols": 3}},
                {"type": "label", "slot": "caption_band",
                 "params": {"en": "≈20% electricity · ≈80% heat", "ur": "تقریباً 20% بجلی · 80% گرمی"}},
            ],
            "actions": [
                {"action": "efficiency_bar", "params": {}},
                {"action": "heat_arrows", "params": {}},
                {"action": "array_expand", "params": {}},
            ],
            "character": {"pose": "present", "slot": "char_left"},
        },
        {
            "id": "recap",
            "purpose": "recap",
            "headline": {"en": "Light in, current out", "ur": "روشنی اندر، کرنٹ باہر"},
            "narration": {
                "en": "Light in, electrons moving, an inverter shaping the current, and a battery holding it: that is how a solar panel powers a home.",
                "ur": "روشنی اندر، الیکٹران حرکت میں، انورٹر کرنٹ کو درست کرتا ہوا، اور بیٹری اسے سنبھالے ہوئے: یوں سولر پینل گھر کو بجلی دیتا ہے۔",
            },
            "elements": [
                {"type": "panel", "slot": "stage_left", "params": {"rows": 3, "cols": 3}},
                {"type": "inverter", "slot": "stage_mid"},
                {"type": "battery", "slot": "stage_right"},
                {"type": "house", "slot": "house_small"},
                {"type": "recap_flow", "slot": "stage"},
            ],
            "actions": [
                {"action": "flow_recap", "params": {}},
            ],
            "character": {"pose": "celebrate", "slot": "char_left"},
        },
    ],
)

# ===========================================================================
# WI-FI / WIRELESS NETWORKING
# ===========================================================================
_pack(
    id="wifi",
    world="wifi",
    palette="tech",
    match=["wi-fi", "wifi", "wireless", "router", "internet", "radio waves", "5g", "network",
           "وائی فائی", "وائفائی", "روٹر", "انٹرنیٹ", "نیٹ ورک"],
    title={"en": "How Wi-Fi Moves Data Through the Air", "ur": "وائی فائی ہوا میں ڈیٹا کیسے بھیجتی ہے"},
    keywords={"en": ["radio waves", "gigahertz", "modulation", "packet", "channel"],
              "ur": ["ریڈیو لہریں", "گیگاہرٹز", "ماڈیولیشن", "پیکٹ", "چینل"]},
    scenes=[
        {
            "id": "hook",
            "purpose": "hook",
            "headline": {"en": "No cable, still connected", "ur": "تار نہیں، پھر بھی جڑے ہوئے"},
            "narration": {
                "en": "Your phone has no cable, yet a video plays without a pause. The signal reaches it as radio waves, moving through the air of the room.",
                "ur": "آپ کے فون میں کوئی تار نہیں، پھر بھی ویڈیو بغیر رکے چلتی ہے۔ سگنل اس تک ریڈیو لہروں کی صورت میں پہنچتا ہے، جو کمرے کی ہوا میں سفر کرتی ہیں۔",
            },
            "elements": [
                {"type": "room", "slot": "back"},
                {"type": "router", "slot": "router"},
                {"type": "device", "slot": "device", "params": {"kind": "phone"}},
                {"type": "waves", "slot": "link", "params": {"count": 4}},
            ],
            "actions": [
                {"action": "router_boot", "params": {}},
                {"action": "waves_emit", "params": {}},
                {"action": "packet_arrives", "params": {}},
            ],
            "character": {"pose": "point_right", "slot": "char_left"},
        },
        {
            "id": "radio",
            "purpose": "explain",
            "headline": {"en": "Data rides on radio waves", "ur": "ڈیٹا ریڈیو لہروں پر سوار ہے"},
            "narration": {
                "en": "A router sends data as radio waves, commonly at two point four or five gigahertz. The wave carries encoded bits, not sound.",
                "ur": "روٹر ڈیٹا کو ریڈیو لہروں کی صورت میں بھیجتا ہے، عام طور پر دو اعشاریہ چار یا پانچ گیگاہرٹز پر۔ لہر کوڈ شدہ بٹس لے کر جاتی ہے، آواز نہیں۔",
            },
            "elements": [
                {"type": "router", "slot": "stage_left"},
                {"type": "device", "slot": "stage_right", "params": {"kind": "laptop"}},
                {"type": "waves", "slot": "link", "params": {"count": 6, "band": "5 GHz"}},
                {"type": "label", "slot": "caption_band", "params": {"en": "2.4 GHz · 5 GHz", "ur": "2.4 گیگاہرٹز · 5 گیگاہرٹز"}},
            ],
            "actions": [
                {"action": "waves_emit", "params": {}},
                {"action": "frequency_shift", "params": {}},
                {"action": "packet_encode", "params": {}},
            ],
            "character": {"pose": "present", "slot": "char_right"},
        },
        {
            "id": "modulation",
            "purpose": "explain",
            "headline": {"en": "Switching the wave = bits", "ur": "لہر کو آن آف کرنا = بٹس"},
            "narration": {
                "en": "The router switches the wave on and off, or shifts its phase, millions of times each second. This is modulation, and the receiver reads the pattern as ones and zeros.",
                "ur": "روٹر لہر کو ہر سیکنڈ لاکھوں بار آن اور آف کرتا ہے، یا اس کا مرحلہ بدلتا ہے۔ اسی کو ماڈیولیشن کہتے ہیں، اور وصول کرنے والا اس نمونے کو ایک اور صفر کے طور پر پڑھتا ہے۔",
            },
            "elements": [
                {"type": "waveform", "slot": "stage", "params": {"kind": "modulated", "bits": "1011001"}},
                {"type": "bit_stack", "slot": "stage_right", "params": {"bits": "1011001"}},
                {"type": "router", "slot": "stage_left"},
            ],
            "actions": [
                {"action": "bits_appear", "params": {}},
                {"action": "modulate_wave", "params": {}},
                {"action": "decode_bits", "params": {}},
            ],
            "character": {"pose": "think", "slot": "char_left"},
        },
        {
            "id": "sharing",
            "purpose": "explain",
            "headline": {"en": "One channel, many devices", "ur": "ایک چینل، کئی ڈیوائسز"},
            "narration": {
                "en": "Many devices share one channel. Before sending, a device listens. If the channel is busy it waits, so packets do not collide.",
                "ur": "ایک ہی چینل کئی ڈیوائسز استعمال کرتی ہیں۔ بھیجنے سے پہلے ڈیوائس سنتی ہے۔ اگر چینل مصروف ہو تو وہ انتظار کرتی ہے، تاکہ پیکٹ آپس میں نہ ٹکرائیں۔",
            },
            "elements": [
                {"type": "router", "slot": "slot_a"},
                {"type": "device", "slot": "slot_b", "params": {"kind": "laptop"}},
                {"type": "device", "slot": "slot_c", "params": {"kind": "phone"}},
                {"type": "device", "slot": "slot_d", "params": {"kind": "tv"}},
                {"type": "waves", "slot": "link", "params": {"count": 3}},
                {"type": "label", "slot": "caption_band", "params": {"en": "listen → wait → send", "ur": "سنیں ← انتظار ← بھیجیں"}},
            ],
            "actions": [
                {"action": "devices_join", "params": {}},
                {"action": "channel_listen", "params": {}},
                {"action": "packets_share", "params": {}},
            ],
            "character": {"pose": "present", "slot": "char_right"},
        },
        {
            "id": "range",
            "purpose": "example",
            "headline": {"en": "Walls weaken the signal", "ur": "دیواریں سگنل کمزور کرتی ہیں"},
            "narration": {
                "en": "Walls and distance weaken the signal. Five gigahertz is faster but has shorter range; two point four gigahertz travels further but carries less data.",
                "ur": "دیواریں اور فاصلہ سگنل کمزور کر دیتے ہیں۔ پانچ گیگاہرٹز تیز ہے مگر کم فاصلے تک جاتا ہے؛ دو اعشاریہ چار گیگاہرٹز دور تک جاتا ہے مگر کم ڈیٹا لے جاتا ہے۔",
            },
            "elements": [
                {"type": "room", "slot": "back", "params": {"walls": True}},
                {"type": "router", "slot": "stage_left"},
                {"type": "device", "slot": "stage_right", "params": {"kind": "phone"}},
                {"type": "waves", "slot": "link", "params": {"count": 5, "attenuate": True}},
                {"type": "signal_bars", "slot": "caption_band", "params": {"level": 0.45}},
            ],
            "actions": [
                {"action": "walls_block", "params": {}},
                {"action": "signal_drop", "params": {}},
                {"action": "band_compare", "params": {}},
            ],
            "character": {"pose": "think", "slot": "char_right"},
        },
        {
            "id": "recap",
            "purpose": "recap",
            "headline": {"en": "Bits become waves, waves become bits", "ur": "بٹس لہریں بنتے ہیں، لہریں بٹس"},
            "narration": {
                "en": "Bits become waves at the router, travel through the room, and are turned back into bits by your device. No cable, just carefully shaped radio.",
                "ur": "روٹر پر بٹس لہریں بنتے ہیں، کمرے میں سفر کرتے ہیں، اور آپ کی ڈیوائس انہیں واپس بٹس میں بدل دیتی ہے۔ کوئی تار نہیں، صرف سوچی سمجھی ریڈیو لہر۔",
            },
            "elements": [
                {"type": "router", "slot": "stage_left"},
                {"type": "device", "slot": "stage_right", "params": {"kind": "phone"}},
                {"type": "waves", "slot": "link", "params": {"count": 5}},
                {"type": "bit_stack", "slot": "bit_trail", "params": {"bits": "1011 0100"}},
            ],
            "actions": [
                {"action": "flow_recap", "params": {}},
            ],
            "character": {"pose": "celebrate", "slot": "char_left"},
        },
    ],
)

# ===========================================================================
# BRIDGE ENGINEERING
# ===========================================================================
_pack(
    id="bridge",
    world="bridge",
    palette="blueprint",
    match=["bridge", "truss", "suspension", "beam", "span", "load", "civil engineering",
           "پل", "پُل", "ٹرس", "سسپنشن", "بوجھ"],
    title={"en": "How a Bridge Carries Weight", "ur": "پل وزن کیسے اٹھاتا ہے"},
    keywords={"en": ["load", "compression", "tension", "truss", "cables"],
              "ur": ["بوجھ", "کمپریشن", "ٹینشن", "ٹرس", "کیبلز"]},
    scenes=[
        {
            "id": "hook",
            "purpose": "hook",
            "headline": {"en": "Tonnes of traffic, held above water", "ur": "ٹنوں ٹریفک، پانی کے اوپر"},
            "narration": {
                "en": "A bridge holds tonnes of traffic above water. It stays up because every part pushes or pulls against another part.",
                "ur": "ایک پل پانی کے اوپر ٹنوں ٹریفک اٹھائے رکھتا ہے۔ یہ قائم رہتا ہے کیونکہ ہر حصہ دوسرے حصے کو دھکیلتا یا کھینچتا ہے۔",
            },
            "elements": [
                {"type": "valley", "slot": "back"},
                {"type": "bridge", "slot": "bridge", "params": {"kind": "truss", "spans": 3}},
                {"type": "truck", "slot": "deck"},
            ],
            "actions": [
                {"action": "build_bridge", "params": {}},
                {"action": "truck_drives", "params": {}},
                {"action": "load_highlight", "params": {}},
            ],
            "character": {"pose": "point_right", "slot": "char_left"},
        },
        {
            "id": "loads",
            "purpose": "explain",
            "headline": {"en": "Two loads: dead and live", "ur": "دو بوجھ: ڈیڈ اور لائیو"},
            "narration": {
                "en": "Two loads matter. The dead load is the bridge's own weight. The live load is everything that moves across it: trucks, buses, people.",
                "ur": "دو بوجھ اہم ہیں۔ ڈیڈ لوڈ پل کا اپنا وزن ہے۔ لائیو لوڈ وہ سب ہے جو اس پر چلتا ہے: ٹرک، بسیں، لوگ۔",
            },
            "elements": [
                {"type": "valley", "slot": "back"},
                {"type": "bridge", "slot": "bridge", "params": {"kind": "beam", "spans": 3}},
                {"type": "weight_arrows", "slot": "deck", "params": {"kind": "dead"}},
                {"type": "truck", "slot": "deck"},
            ],
            "actions": [
                {"action": "dead_load", "params": {}},
                {"action": "live_load", "params": {}},
                {"action": "sum_load", "params": {}},
            ],
            "character": {"pose": "present", "slot": "char_right"},
        },
        {
            "id": "compression",
            "purpose": "explain",
            "headline": {"en": "Piers take compression", "ur": "ستون کمپریشن اٹھاتے ہیں"},
            "narration": {
                "en": "Weight pushes down on the deck. The piers carry that force in compression, squeezing the material, while the deck bends and is stretched in tension.",
                "ur": "وزن ڈیک کو نیچے دھکیلتا ہے۔ ستون یہ قوت کمپریشن میں اٹھاتے ہیں، یعنی مادے کو دباتے ہیں، جبکہ ڈیک جھکتا ہے اور نیچے سے کھنچتا ہے۔",
            },
            "elements": [
                {"type": "valley", "slot": "back"},
                {"type": "bridge", "slot": "bridge", "params": {"kind": "beam", "spans": 2, "stress": True}},
                {"type": "force_arrows", "slot": "pier", "params": {"kind": "compression"}},
                {"type": "force_arrows", "slot": "deck", "params": {"kind": "bending"}},
            ],
            "actions": [
                {"action": "load_push", "params": {}},
                {"action": "compression", "params": {}},
                {"action": "bending", "params": {}},
            ],
            "character": {"pose": "think", "slot": "char_left"},
        },
        {
            "id": "truss",
            "purpose": "explain",
            "headline": {"en": "Triangles keep their shape", "ur": "مثلث اپنی شکل رکھتے ہیں"},
            "narration": {
                "en": "A triangle cannot change shape unless one of its sides changes length. A truss built from triangles spreads the load along its members without collapsing.",
                "ur": "مثلث اپنی شکل نہیں بدل سکتا جب تک اس کی کوئی ضلع اپنی لمبائی نہ بدلے۔ مثلثوں سے بنا ٹرس بوجھ کو گرنے کے بغیر اس کے ارکان میں پھیلا دیتا ہے۔",
            },
            "elements": [
                {"type": "valley", "slot": "back"},
                {"type": "bridge", "slot": "bridge", "params": {"kind": "truss", "spans": 2, "stress": True}},
                {"type": "member_forces", "slot": "truss", "params": {}},
            ],
            "actions": [
                {"action": "triangles_form", "params": {}},
                {"action": "member_forces", "params": {}},
                {"action": "load_spread", "params": {}},
            ],
            "character": {"pose": "point_right", "slot": "char_right"},
        },
        {
            "id": "suspension",
            "purpose": "example",
            "headline": {"en": "Cables pull, towers push", "ur": "کیبلز کھینچتی ہیں، ٹاور دباتے ہیں"},
            "narration": {
                "en": "In a suspension bridge the deck hangs from cables. The cables are in tension, so they pull the towers inward, and the towers push the load into the ground.",
                "ur": "سسپنشن پل میں ڈیک کیبلز سے لٹکتا ہے۔ کیبلز ٹینشن میں ہوتی ہیں، اس لیے وہ ٹاورز کو اندر کی طرف کھینچتی ہیں، اور ٹاور وزن کو زمین میں اتار دیتے ہیں۔",
            },
            "elements": [
                {"type": "valley", "slot": "back"},
                {"type": "bridge", "slot": "bridge", "params": {"kind": "suspension", "spans": 2, "stress": True}},
                {"type": "force_arrows", "slot": "cable", "params": {"kind": "tension"}},
            ],
            "actions": [
                {"action": "cables_tense", "params": {}},
                {"action": "tower_push", "params": {}},
                {"action": "load_path", "params": {}},
            ],
            "character": {"pose": "present", "slot": "char_left"},
        },
        {
            "id": "recap",
            "purpose": "recap",
            "headline": {"en": "Load in, load into the ground", "ur": "بوجھ اندر، بوجھ زمین میں"},
            "narration": {
                "en": "Load comes in, members push or pull, and the ground takes the final force. Choose the shape that carries your load: beam, truss, arch or suspension.",
                "ur": "بوجھ آتا ہے، ارکان دھکیلتے یا کھینچتے ہیں، اور آخری قوت زمین سنبھال لیتی ہے۔ اپنے بوجھ کے مطابق شکل چنیں: بیم، ٹرس، محراب یا سسپنشن۔",
            },
            "elements": [
                {"type": "valley", "slot": "back"},
                {"type": "bridge", "slot": "bridge", "params": {"kind": "suspension", "spans": 3}},
                {"type": "weight_arrows", "slot": "deck", "params": {"kind": "mixed"}},
            ],
            "actions": [
                {"action": "flow_recap", "params": {}},
            ],
            "character": {"pose": "celebrate", "slot": "char_right"},
        },
    ],
)


def list_packs() -> List[Dict[str, str]]:
    return [{"id": p["id"], "world": p["world"], "title_en": p["title"]["en"], "title_ur": p["title"]["ur"]} for p in PACKS]


def find_pack(topic: str) -> Optional[Dict[str, Any]]:
    """Substring/keyword match, longest keyword wins."""
    t = topic.lower().strip()
    best: Optional[Dict[str, Any]] = None
    best_len = 0
    for pack in PACKS:
        for kw in pack["match"]:
            k = kw.lower()
            if k and k in t and len(k) > best_len:
                best = pack
                best_len = len(k)
    return best
