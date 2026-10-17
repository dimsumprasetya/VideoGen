"""Bahasa film untuk penulis AI: struktur 3 babak Hollywood klasik, hubungan antar shot (editing kontinuitas),
mise en scene, sinematografi dan suara. Diringkas dari materi Kusen Dony Hermansyah (Konsep Penceritaan,
Mise en Scene, Sinematografi, Teori Dasar Editing Film, Dasar Suara Film).

Catatan: di aplikasi ini satu "scene" = satu klip AI (3-12 dtk) = praktis satu SHOT. Maka aturan hubungan
antar shot berlaku di antara scene yang berurutan."""

# Beat struktur 3 babak (urutan = urutan cerita). point_of_attack = scene pendek di akhir babak 1 yang mengubah
# tujuan tokoh dan membawa masuk ke babak 2.
# recap (serial: "previously on") membuka episode lanjutan; cliffhanger menutup episode serial (bukan resolution).
STORY_BEATS = ["recap", "opening_image", "setup", "inciting_incident", "point_of_attack", "rising_action", "midpoint",
               "crisis", "climax", "resolution", "cliffhanger"]
BEAT_ACT = {"recap": 1, "opening_image": 1, "setup": 1, "inciting_incident": 1, "point_of_attack": 1,
            "rising_action": 2, "midpoint": 2, "crisis": 2, "climax": 3, "resolution": 3, "cliffhanger": 3}

# Ukuran shot (classical cutting: ELS -> LS -> FS -> MS -> MCU -> CU -> BCU -> ECU), sudut, gerak kamera, arah gerak.
SHOTS = ["Extreme long shot", "Long shot", "Full shot", "Medium long shot", "Medium shot", "Medium close-up",
         "Close-up", "Big close-up", "Extreme close-up", "Two shot", "Over-the-shoulder", "POV", "Insert"]
ANGLES = ["Eye level", "High angle", "Low angle", "Bird's eye", "Worm's eye", "Dutch angle"]
CAMS = ["Static", "Pan", "Tilt", "Track in", "Track out", "Track lateral", "Crane up", "Crane down", "Handheld",
        "Steadicam", "Orbit", "Rack focus"]
DIRS = ["static", "left to right", "right to left", "toward camera", "away from camera"]

# Hubungan ke shot berikutnya. Cut-to-cut: cut in / cut away / match on action / match cut / eyeline match /
# shot reverse shot / sound bridge / parallel cut. Optical effect: dissolve / fade to black / wipe.
TRANSITIONS = ["cut", "cut in", "cut away", "match on action", "match cut", "eyeline match", "shot reverse shot",
               "sound bridge", "parallel cut", "dissolve", "fade to black", "wipe"]

# Nilai lama (versi sebelumnya) -> nilai baru
OLD = {"Wide": "Long shot", "Medium": "Medium shot", "Top-down": "Long shot", "Push-in": "Track in",
       "Pull-out": "Track out", "Tracking": "Track lateral", "action cut": "match on action",
       "eyeline cut": "eyeline match", "whip pan": "wipe"}


def norm(value, allowed, default):
    """Nilai dari LLM/proyek lama -> salah satu `allowed` (tidak peka huruf besar/kecil)."""
    v = OLD.get(str(value or "").strip(), str(value or "").strip())
    for a in allowed:
        if a.lower() == v.lower():
            return a
    return default


CRAFT = """FILM GRAMMAR - follow strictly. In this video every scene is ONE shot (one AI clip), so the rules for
cutting between shots apply between consecutive scenes.

STORY (classic Hollywood three-act structure, causal and progressive):
- One protagonist is the agent of cause and effect, with a clear goal, need and desire; an antagonist or an
  obstacle (active or passive) blocks the goal; conflict = goal meets obstacle.
- Act 1 (~25% of running time): opening_image (visual hook within 3 s that already shows WHO, WHERE, WHEN and
  the problem), setup, inciting_incident, point_of_attack (short beat that changes the protagonist's goal and
  pushes into act 2).
- Act 2 (~50%): rising_action in waves of tension and release that keep escalating, midpoint (twist/discovery
  that raises the stakes), crisis (lowest point, hardest choice).
- Act 3 (~25%): climax (decisive action that answers the dramatic question), resolution (closure; the final
  image echoes or mirrors the opening image).
- Every scene is caused by the previous one and causes the next: write links with "because / therefore / but",
  never "and then". Acts never go backwards.
- Repeat key information by duplication (same idea, new situation, higher stakes), not repetition. Plant
  setups that pay off later; a recurring visual or sound motif (leitmotif) ties the story together. Control
  information: tell the audience something the character does not know for suspense, or withhold it for surprise.

SHOT RELATIONSHIPS (continuity editing):
- Each NEW location starts with an establishing shot (Extreme long / Long / Full shot) unless the cut is a
  deliberate match cut or POV; then go closer step by step (classical cutting: LS -> FS -> MS -> MCU -> CU -> ECU),
  use CU/ECU only for dramatic emphasis.
- Never cut between two shots of the same subject with the same shot size and angle (jump cut): change size or
  move the angle at least 30 degrees.
- 180-degree rule: keep screen direction. A character looking or moving left-to-right keeps that direction in
  the next shot; two characters keep their left/right positions. A change of direction must be seen in frame.
- Eyeline match / POV: when a character looks at something, the next shot shows what they see.
- Shot / reverse shot for dialogue (over-the-shoulder or MCU of each speaker, same side of the line).
- Match on action: cut in the middle of a movement and continue it. Match cut: same shape, color or motion
  across the cut. Cut away / insert: a detail or reaction shot that adds information (a neutral face gains
  meaning from the shot next to it).
- Time and place jumps need a bridge: dissolve (time passes), fade to black (big jump / ending), wipe,
  sound bridge (dialog, VO or a sound continues over the cut), or parallel cut (meanwhile elsewhere).
- Rhythm: Act 1 moderate shot lengths, Act 2 shots get shorter as tension rises, climax shortest (accelerating
  rhythm), resolution longer and calmer.

MISE EN SCENE & CINEMATOGRAPHY:
- Setting, props and costume tell place, time period, time of day and social status; keep them consistent
  (costume includes props held by the character; nothing out of place in a set).
- Lighting is motivated by a visible source and the time of day (morning daylight bluish-white, sunset amber
  tungsten, night practical lights); keep the key light direction consistent within a location. High-key, low
  contrast for light/comic moods; low-key, high contrast for tension or fear.
- Make the point of interest the brightest, largest, most contrasting or moving element; compose with the rule of
  thirds and leading lines; use selective or rack focus to guide the eye.
- Shot size by purpose: ELS/LS = where we are, FS = whole-body gesture, MS = action, MCU = normal dialogue,
  CU/BCU/ECU = emotion and emphasis. Angle by meaning: eye level = neutral, high angle = character small or weak,
  low angle = powerful or threatening, Dutch angle = instability. Camera moves only with a motivation
  (follow action, reveal space, approach emotion); static when the action itself carries the shot.
- Show emotion through gesture and facial expression, not explanation.

SOUND:
- Speech: dialogue (on screen), VO / narrator (off screen, outside the story world), off-screen voice of another
  character, interior monologue (thoughts). Do not let a character announce what they are about to do.
- sound (English) = diegetic effects and ambience that make the space and time real (footsteps, wind, birds at
  dawn, rain, traffic, room tone) and support the mood; a sound may continue over the cut as a bridge."""


CLIFF = """SERIES RULES (continuing serial with cliffhangers):
- Every episode is a complete mini three-act story: its own dramatic question is answered at the climax. Only the
  LAST beat (cliffhanger) opens a bigger question that the next episode must answer. Never resolve the cliffhanger.
- Cliffhanger types: reveal (a truth changes everything), danger (the protagonist in immediate peril), choice (an
  impossible decision), arrival/betrayal (an unexpected person or act), loss/vanishing (someone or something is gone).
  Show it visually in the last 2-4 seconds of the final scene and cut at the peak (smash cut or fade to black).
- Control information: either the audience knows something the characters do not (suspense), or we see the shocking
  image without explanation (surprise). Each cliffhanger raises the stakes above the previous episode's.
- A continuing episode opens with a recap beat (1-2 very short shots, at most 4 seconds in total, recalling the previous
  cliffhanger with the same costumes and place), then pays the cliffhanger off in the first scenes of act 1. Do not
  repeat information the audience already has beyond that recap.
- Continuity: the STATE LEDGER and SERIES BIBLE are law. Characters keep their looks, wardrobe, injuries, objects,
  knowledge, relationships, place and time of day unless a time skip is shown. Use the same names."""


def story_text_rules():
    """Ringkasan aturan cerita saja (storyline)."""
    return CRAFT.split("SHOT RELATIONSHIPS")[0].strip()
