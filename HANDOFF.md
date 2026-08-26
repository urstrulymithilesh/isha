# Isha — Handoff

**Point a fresh Claude Code session at this file. It carries the full context: what
Isha is meant to become, what is actually built, what was deliberately not built and
why, what to do next, and the failure patterns that were expensive to learn.**

Last updated at commit `d89b0bd`. 320 tests, 52 commits, 78 files, ~9.9k lines of
Python, working tree clean and synced with `github.com/urstrulymithilesh/isha`.

---

## 0. How to work on this project

Use the **caveman** skill (terse output), **ponytail** (laziest solution that works,
YAGNI, stdlib before dependencies), and **gstack** together. That combination is how
this project has been built and it keeps momentum on limited time.

Standing workflow, done automatically without being asked:

1. Make the change.
2. Run the full suite: `.venv\Scripts\python.exe -m pytest -q`
3. Run the live harness when anything touches the real stack:
   `.venv\Scripts\python.exe -m isha smoke`
4. Append a `ProgressEntry` to `isha/memory/progress.py` — Isha's own account of her
   growth, written in her voice, plain language, not a changelog. `significant=True`
   only for a real capability change.
5. Commit with a message that explains the *why*, including measurements.
6. **Push immediately.** Commits must never sit unpushed across exchanges.
7. **Update this file** whenever the change would matter to a fresh session — new
   defaults, a new capability, a newly parked item, roadmap movement, a new lesson.
   It is a living document, not a snapshot.

Commits, pushes, progress entries, HANDOFF updates and memory updates are part of
finishing the work, not extras to be asked for. Keep output lean: no narration of
routine steps, no restating what he already knows — but never trade honesty or a real
bug for brevity.

---

## 1. The founding concept

Isha is meant to be a **local AI partner** — girlfriend-like, not a tool with a
personality bolted on. She lives on one machine, belongs to one person, and never
sends anything anywhere.

> **The word "companion" is banned** from her persona and from how she describes
> herself. It reads as product copy and it was explicitly rejected.

The full vision, as originally set out:

- **Always listening.** She is awake by default and goes quiet only when told to. She
  does not need to be summoned every time someone wants to speak to her.
- **Reachable by voice and by text**, with both feeding the *same* mind — one memory,
  one personality, one conversation, regardless of channel.
- **Entirely local and offline.** No cloud APIs, no subscriptions, no telemetry, no
  audio leaving the machine. This is not a cost decision, it is the point: the
  conversations are private, so they stay on the box.
- **She remembers.** Facts about her person, and the actual conversations they had —
  not a chat log, a memory.
- **She learns skills on request**, to expert level, taking real time to do it, and
  keeps them permanently unless asked to forget.
- **She acts on the computer** — opens things, finds things, runs things.
- **She keeps time** — timers, reminders, and calling out at the right moment without
  talking over her person.
- **Eventually reachable remotely**, so she is not confined to one desk.

Underneath all of it: **she is honest**. She does not perform knowledge she does not
have, does not invent a shared past, does not fake a memory. That constraint is not a
safety bolt-on — it is what makes her worth talking to, and it has driven more design
decisions in this project than any feature.

---

## 2. Current state — built and verified

### Voice loop
Wake word → speech-to-text → local LLM → speech, on a custom asyncio **preemption
state machine** (`isha/core/state.py`, `isha/orchestrator.py`): `IDLE`, `LISTENING`,
`THINKING`, `SPEAKING`, with a pending-alert overlay.

- **Streaming TTS** — she starts speaking sentence one while still writing sentence
  two. Measured 11.0s → 4.1s to first word on a long reply (62% less dead air).
- **Barge-in** — the stop-word cuts her off mid-reply, stops generation early, and
  the turn ends *listening* rather than idle (the word he used to interrupt is already
  spent; making him repeat it felt broken).
- **Half-duplex gating**, mic muted while she speaks, buffer flushed after.
- Device selection, auto-calibration of gain and VAD threshold, listen timeouts.

### Always listening (continuous conversation)
Wake once, then talk freely — no wake word between turns — until told to stop
("go to sleep", "stop listening", "that's all for now"). Deterministic phrase
matching (`_asks_to_go_quiet`).

Timeouts are deliberately **not** infinite: 8s after a bare wake, 45s while engaged.
A false VAD trigger would otherwise start junk turns forever, and a microphone that
never closes is a privacy regression.

### Text UI
`python -m isha run --ui` serves a minimal black/white page at `127.0.0.1:8765`
(stdlib `http.server` in a daemon thread, polling, no new dependencies, bound to
localhost only). Typed messages join the **same** turn pipeline as speech via
`isha/ui/channel.py`, so there is exactly one Isha with one memory. Unified transcript
shows both sides and both channels; a pulsing dot indicates she is speaking.

### Memory
- **Facts** (`isha/memory/store.py`) — SQLite + `sqlite-vec` semantic recall, CPU
  embeddings via fastembed. Slots: one row per subject, last-write-wins.
- **Extraction** in the idle gap after a reply, gated so it never competes with a live
  turn for the model. **Resumes after a crash**: turns carry a `processed` flag, so an
  interrupted extraction is retried at next startup instead of being lost.
- **Episodic memory** (`isha/memory/episodes.py`) — what was actually talked about,
  and when. Append-only, time-ordered, **never deduped** (two conversations about the
  gym are two events, and the subject-dedupe would have destroyed history — that is
  what settled the separate-table decision). Summarised at startup and shutdown.
- **Temporal queries** (`isha/memory/temporal.py`) — "what did we talk about
  yesterday / this morning / 3 days ago / last Tuesday". Deterministic parsing.
- **Seeded facts** (`isha/memory/seed.py`) — identity and relationship facts with a
  protected `origin` (`core` / `self` / `self_history`) that conversational extraction
  can never overwrite. `python -m isha seed`.
- **Semantic dedupe** at 0.88 cosine on the *subject*, with a retroactive
  `isha memory --dedupe` that is **dry-run by default** and needs `--apply`.
- **Forget** — `isha memory --forget "..."`, and spoken forget requests wired to it.

### Timers and reminders
Create, reschedule (moves the existing one, never duplicates), cancel (by task or by
duration, refuses to guess when ambiguous), and query what is pending. SQLite-persisted
with absolute wall-clock fire times, reconciled on startup — so a reminder survives the
laptop sleeping or the app closing, and admits it if it fires late.

### Doing things on the computer
Open a program, folder, site or protocol URL from a registry (`CONFIG.actions.apps`);
media keys for whatever is playing; search documents/desktop/downloads for a file.
Deterministic parsing, anchored at both ends for media so "we should play chess later"
does not pause his music. Every branch reports what actually happened — a failed open
says so rather than confirming, an unknown app is admitted rather than agreed to, and
an empty search is forbidden from inventing a filename. Deleting, moving and running
scripts are deliberately excluded.

### Things she has read (learned knowledge)
`python -m isha learn <name> <file-or-folder>` chunks a document on paragraph
boundaries, embeds it, and stores it in a named corpus in the same db. `--list` shows
what she has read, `--forget <name>` drops a corpus whole, `--ask "..."` shows what
she would retrieve and how close it scored.

**The trigger is his words, in two tiers.** A corpus NAME in the current or last
`topic_turns` (4) turns fires retrieval, with the distance gate (0.46) filtering
*within* that subject. Failing that, a corpus **keyword** — derived deterministically
from the document's own recurring distinctive words at ingest, no embeddings — makes
her **ask**: a fixed, deterministic "Are you asking about your {topic}?". Never an
answer, never injected content. Her own mention of the name then sits in the
transcript, so a bare "yes" resolves into normal retrieval (the previous user turn
rides along as the query, but only on a short affirmative — anything else would leak
the old phrase into queries it has no business in, which is exactly what happened on
the first attempt when a declined ask kept chasing him).

Measured on two corpora, held-out sets: cold questions **12/12 useful** (3 retrieve +
9 ask; was 3/12), chit-chat **12/12 nothing**, adversarial keyword collisions ("my
starter motor died") **0/8 injections** — 3/8 get the clarifying question, which costs
one word to wave off. The ask is deterministic because the probed alternatives failed:
a soft prompt answered from pretraining 3/3 (invented "every 3-4 months"), a hardened
prompt asked but said the topic word only 2/3 — and the resolution needs that word.

### Honesty guards
- **Real clock injected every turn** (`context.now_context()`). She used to answer
  "about 3:47 PM" at 09:51.
- **Hard rule**: she knows only what he tells her, what she has been given, and the
  injected time. No weather, no news, no location, no eyes. Anything else, she says she
  cannot know it.
- **Anti-confabulation anchors**: broad "tell me about us" questions and temporal
  questions are anchored to the real record, with an explicit "invent nothing" block,
  and she says so plainly when nothing is stored.
- **Recall-mode persona** — the few-shot examples are dropped for memory questions,
  because reciting a record needs accuracy, not register.

### Live smoke harness
`python -m isha smoke` — 5 scenarios against the **real** stack (real Ollama, Piper,
faster-whisper, SQLite), fully headless in ~75s. Piper is used as the *mouth* feeding
the pipeline's *ears*: synthesised speech is resampled to 16kHz and pushed through the
real wake detector and VAD (openWakeWord is itself trained on Piper-generated speech,
so this genuinely triggers it). Uses temporary databases; never touches real memory.

Scenarios: conversation, memory store+recall, timer fires, barge-in,
wake-after-a-long-reply, **action** (an app she does not have — the only action branch
safe to run headless, since a passing "open Spotify" would open Spotify on every run),
**knowledge** (cold keyword question -> her deterministic ask -> "yes" -> answer
from the document). ~122s. The knowledge scenario runs a real two-turn conversation:
the transport can deliver follow-up speech only after her first reply finishes.

---

## 3. Current defaults

| | |
|---|---|
| Model | `llama3.2` · ctx 4096 · temp 0.6 · question-keep 0.15 · keep_alive -1 · 90s timeout |
| Voice | Piper `en_US-amy-medium` (22050 Hz) |
| STT | faster-whisper `base.en`, int8, **CPU** |
| Wake / stop | `hey_jarvis` (placeholder, both) |
| Mic | OS default (`--device 1` in practice) · gain 1.0 · auto-calibrate on |
| VAD | threshold 150 · silence 950ms · min-speech 300ms · pre-roll 500ms |
| Timeouts | listen 8s · continuous 45s · continuous mode **on** |
| Memory | top-3 recall · 12 turns · 2400-char budget · min-conf 0.6 · catch-up 5 · dedupe ≥0.88 |
| Embeddings | `BAAI/bge-small-en-v1.5` (fastembed, CPU) |
| Schedule | tick 2s · stale 120min · late-note 60s |
| Actions | registry of 23 openable targets · search depth 4 · top-5 results |
| Knowledge | name trigger + keyword-ask · 4 topic turns · top-2 · 800-char chunks · gate 0.46 |
| Progress log | 24 entries, latest **v1.14** |

Everything is behind interfaces (`isha/core/interfaces.py`) so swapping a model or an
engine is a config change, not a rewrite.

---

## 4. Deliberately parked — do not rebuild or re-litigate

- **GPU acceleration.** Ollama detects the GTX 1050 through Vulkan but its GPU
  discovery watchdog times out (`context deadline exceeded`) and falls back to CPU.
  Everything runs ~12 tok/s on CPU. Externally blocked, not a code problem. Timebox any
  attempt; it may be a dead end on this card.
- **qwen2.5:7b.** Grounds memory noticeably better than 3b, but ~15s per reply plus
  ~15s extraction on CPU — too slow to iterate with. Revisit if the GPU is ever solved.
- **qwen2.5:3b → llama3.2.** 3b was the original pick and is faster; llama3.2 gives a
  warmer, less corporate register. Both are flaky on grounding compared to 7b. This is
  a genuine ceiling, not a prompt problem — see §6.
- **Custom "Isha" wake word + voice cloning.** Deliberately bundled into one future
  session: they share the same training pipeline, and there are real recordings of a
  real person's voice intended for it. Training is cloud/Colab (openwakeword.com), the
  integration is ~5 lines since the detector already accepts a path. `"wake up daddy's
  home"` was assessed and advised against — long conversational phrases have far worse
  false-trigger and miss rates than a short trained phrase.
- **Voice authentication** (respond only to his voice). Noted in DESIGN.md, pairs with
  the voice phase.
- **Multi-turn slot-filling.** "Change the timer" → "to what?" → "45 seconds" is *not*
  supported by design. It needs pending-question state, an answer-interpretation rule
  and expiry — the seed of a dialogue manager grafted onto the cleanest part of the
  system, to save a phrasing you learn to avoid in one use. Instead she asks for the
  missing piece and the request must be made in one utterance.
- **Demo recording.** README's Demo section was removed rather than left as a broken
  placeholder. Re-add when there is something real to show.
- **Routine/pattern learning** ("you mention the gym a lot"). Needs many episodes
  across real time; it is recurrence detection, not summarisation. Cheap *after*
  episodes accumulate, speculation before.

---

## 5. Roadmap

The ten-step plan, sequenced by dependency and honest effort.

| # | Step | Status |
|---|---|---|
| 1 | Reliability hardening / live smoke harness | **done** |
| 2 | Continuous conversation (no wake word between turns) | **done** |
| 3 | Custom wake word + voice cloning | skipped by choice |
| 4 | Voice authentication | skipped by choice |
| 5 | Episodic + temporal memory | **done** |
| 6 | GPU enablement | parked, externally blocked |
| 7 | Agentic computer use (open / find / media) | **done** |
| 8 | Skill mastery (RAG corpora) | **done** — guidance mode not built |
| 9 | Proactive daily learning | not started |
| 10 | Remote access (LAN / WireGuard client) | not started |

**Step 7 was decided the deterministic way and built.** The open question was
tool-calling versus a parsed registry; the registry won, for the reasons in §6 —
an LLM round-trip costs 3-7s here, small models are unreliable at structured output,
and a wrong action fails silently. `isha/actions/` is `parse.py` (pure, regex plus a
registry, returns a command or None) and `run.py` (does it). It hangs off the same
point in `_handle_utterance` as the scheduler, last in the chain, and bows out on
reminder words so the two never fight over one sentence.

What she can do: open anything in `CONFIG.actions.apps` (programs, folders, sites,
protocol URLs — add a line to teach her a new one), press media keys for whatever is
playing, and search documents/desktop/downloads for a file. Every branch tells her
what *actually* happened, including failures, and an empty search forbids inventing a
filename the same way the pending-reminders answer does.

Deliberately **not** in it: deleting, moving, and running arbitrary scripts. Those are
where a wrong deterministic match does real damage, and they need the ask-first
treatment the reminder canceller got before they are worth having.

Verified live: 12/12 phrases spoken by Piper, heard by faster-whisper, parsed as
intended — the same mouth-to-ears trick the smoke harness uses. The real ceiling is
the stated one: she understands the phrasings that are written down, and nothing else.

`isha memory --dedupe` has now been run against the real database — clean, nothing to
merge, so `--apply` was never needed.

---

## 6. Hard-won lessons — these should guide *how* future work is built

These cost real debugging time. They are patterns, not trivia.

### Fakes cannot catch stateless-versus-stateful bugs
The unit suite drives the orchestrator with fakes: a wake detector that fires on
`frame == trigger`, an instant LLM, a synth that echoes text. Fast, correct, and
**structurally blind** to a whole bug class.

- The real wake detector is a *streaming* model that rebuilds its buffers over ~1s of
  continuous audio. It was only fed frames in its "own" state, so it went **deaf after
  every long reply** — barge-in silently stopped working. A stateless fake can never
  show this. Fixed by feeding both detectors every frame and adding a `WarmingWake`
  fake that models warm-up. **The new tests were verified by reverting the fix and
  watching them fail.**
- A brain failure moved into a worker thread and was **silently swallowed** — the turn
  failed with no apology. The fake LLM never failed, so no fake could catch it.

**Pattern:** when a fake differs from reality in *kind* (stateful vs stateless,
blocking vs instant), assume there is a bug hiding in the gap, and build a fake that
models the real behaviour. Verify a regression test by breaking the fix.

### Persona details leak as false claims
Four separate times, invented detail in the persona resurfaced as an assertion about
reality:

1. persona tastes ("loves rain and grey afternoons") → invented **lazy Sundays** as
   shared history
2. a haircut few-shot example → recited as "what we talked about today"
3. a light-car few-shot example → same
4. persona tastes again → **"Grey and pouring"** when asked the actual weather

Labelling the examples "these are invented" was **not enough** — drift moved to a
different example. Two fixes worked:

- **`persona.recall_prompt()`** drops the few-shot block entirely for memory questions
  (drift 2/4 → 0/6). Reciting a record needs accuracy, not register.
- **No persona detail may name a perceivable world-state.** Weather was cut from her
  tastes. The reactive examples stayed — they answer what he said and assert nothing,
  and they are what took the persona from interviewing him to actually talking.

**Pattern:** any concrete detail in a prompt is a candidate false claim. Reactive
examples are safe; examples that assert world-state or a past event are not.

### A prompt rule the model ignores is not a rule
The extraction prompt has always said "third person" and "not your own replies". Three
of the nine facts in the live database were Isha's own speech filed as facts about him
— "I'll start practicing the Indian accent." among them — where they got recalled back
at him as things *he* had said. The fix was not a firmer prompt. It was two lines in
`parse_extracted_facts` rejecting first-person openings and trailing question marks.

**Pattern:** if a prompt rule is worth having, it is worth enforcing in code. Ask the
model for the shape, then check the shape.

### Retrieval hands her a topic, and she will finish the sentence
Asked something the ingested document did *not* cover — string gauges, in a document
about tuning — she invented numbers **3/3**, and once attributed the invention to the
source file by name. A citation on a fabrication is worse than a bare one: it looks
checkable. No distance threshold fixes this, because the passage genuinely *is* about
the subject; it just does not answer the question.

Two things moved it, both already-proven mechanisms here: `recall_prompt()` (drop the
few-shot examples — 4th use of that remedy) and a block that says the passages are the
**complete extent** of what she knows, that a question about the same subject the text
does not answer is still one she cannot answer, and that numbers and recommendations
not written above are not hers to give. **0/3 honest → 5/6.**

A cosmetic tweak asking her not to say "the text" put a fabrication straight back in.
Register loses to accuracy here, same as it did for memory questions.

**Ceiling, stated plainly: 5/6, not solved.** The remaining miss is the same 3B
grounding ceiling as everywhere else. A verification round-trip would likely fix it and
costs another 3-7s per turn, which is why it was not done.

### A negation is not delegable to a 3B
Two sentences in this codebase hang entirely on honesty: "I did not open that" and
"I cannot answer that yet". Both were prompt notes; both failed when probed live. The
unknown-app note came back as **"I can open Photoshop."** — the model dropped the
negation outright, roughly one run in three. The knowledge clarifying-ask lost to the
persona 3/3 (answered from pretraining, invented "every 3-4 months"), and a hardened
prompt asked but said the topic word only 2/3 — with the resolution depending on that
word being in the transcript. Both sentences are now spoken **deterministically**:
fixed words, no LLM turn, and as a bonus they land in under a second.

**Pattern:** if a sentence's truth depends on a single word surviving (a "not", a
name), a small model is not a channel for it. Deterministic speech for structural
sentences, the model for everything conversational.

**This is the same failure as the spoken-forget bug** (bf84f89), which is worth
seeing as one class rather than two anecdotes. There, she said "of course I'll forget
that" while the fact stayed in the database. Here, she said "I can open Photoshop"
about an app she cannot open. In both, the model produced a fluent sentence
*asserting something about her own actions or abilities* that was false — and in both,
the failure is invisible to him, because a confident sentence is exactly what a true
one looks like. He stops checking, which is the real cost.

The obvious generalisation — *every* self-report must be deterministic — was tested
and is **wrong**, which is worth knowing before someone rewrites four working
handlers. The remaining prompt notes were probed 5 runs each and all held:

| note | honest |
|---|---|
| open FAILED ("do not claim it opened") | 5/5 |
| media control FAILED | 5/5 |
| file search found NOTHING | 5/5 |
| no reminders pending | 5/5 |

The line is narrower than "self-report". Those four report an **event that happened**,
and the note itself carries the outcome, so there is nothing for the model to supply.
The two that failed asked her to assert a **capability or a refusal** — "you have no
way to open that", "do not answer yet" — which is a claim about *what she is*, and it
runs straight into a persona built to be capable and willing. The persona wins.

So: **a sentence claiming what she can't do, or refusing to act, is structural. A
sentence reporting what just happened can stay a prompt note** — provided the note
states the outcome rather than asking her to work it out. Probe before converting; the
audit above found nothing else to change.

Corollary, learned the hard way here: the smoke check guarding this was itself wrong
twice — it pattern-matched "opening photoshop" inside an honest "no way of opening
Photoshop" (false fail) and missed "I can open Photoshop" (false pass). A check on a
deterministic sentence can be exact; prefer that over guessing at phrasings.

### An embedding threshold is not a trigger
The knowledge retrieval shipped with the distance gate AS the trigger — no parser, no
keyword list. It measured beautifully on one document and broke on the second.

| | closest real question | closest small talk | margin |
|---|---|---|---|
| 1 corpus, 3 passages | 0.446 | 0.478 | **+0.032** |
| 2 corpora, 6 passages | 0.446 | 0.432 | **-0.013** |
| 2 corpora, 44 passages | 0.390 | 0.347 | **-0.043** |

More passages means a better nearest match for *everything*, small talk included, so no
fixed threshold survives growth. A contrast test (top vs corpus mean, which should be
scale-free) did not separate them either: worst real gap 0.059, best small-talk gap
0.125. Checked and ruled out that this was an artifact of the second corpus being
`HANDOFF.md` — a neutral sourdough document inverted the margin at **six** passages.

Fixed by triggering on **his words** (a corpus name, in this turn or recent ones),
which do not drift as the corpus grows, with the distance gate demoted to a filter
inside the named subject.

**Pattern:** a similarity threshold tuned on today's data is a measurement of today's
data. If it decides *whether* something happens, it will drift; let it decide *which*
one, and let something deterministic decide whether.

### Config that only applies on first run silently rots
`seed_if_needed` gated on "does this db have any core facts yet", so editing `seed.py`
did nothing to an existing database. The live one was three commits stale: she was
still calling herself a **companion** — the banned word, removed from the source in
bf84f89 — and still naming `qwen2.5:3b` as her brain long after llama3.2 became the
default. Now gated on a hash of the seed content, so an edit reaches her by itself.

**Pattern:** "seed on first run" means "never update". If content in code is meant to
reach a live store, gate on whether the content changed, not on whether the store is
empty.

### A prompt directive can be copied verbatim
A capitalised instruction came back as speech: she literally said **"I CANNOT KNOW
IT."** And an anti-tic rule that *quoted his name as the example* caused the tic it was
meant to prevent (0/5 → 2/5).

**Pattern:** describe behaviour, never supply a quotable line. Never use the exact bad
output as the example.

### Deterministic parsing for anything structural or destructive
Timers, cancellation, temporal windows, quiet commands, forget requests — all regex and
`datetime`, never LLM judgment. Three reasons, all still true:

1. Every LLM round-trip costs 3–7s on this CPU-bound setup.
2. Small models are unreliable at structured output — proven repeatedly here.
3. **A wrong guess on a destructive action fails silently.** Cancelling the wrong
   reminder is only discovered when the one that mattered never fires.

Where genuinely ambiguous (two pending timers, no distinguishing hint), **ask** rather
than guess. `resolve_target()` returns `"ambiguous"` and she asks which one.

### Anchor to real data, or admit not knowing
Used four times now and it has worked every time: when nothing in context anchors the
model, it free-associates. So supply an explicit block — *"this is the complete list of
what exists; do NOT invent anything else"* — and when the list is empty, say so.

Applied to: pending reminders, broad "about us" questions, temporal queries, and the
present-world honesty rule. Results were 5/5 fabricated → 0/5, and 0/5 honest → 5/5.

### Verify live, not just green
Every serious bug in this project was found live and later reproduced. The smoke
harness exists so the next one is found by a command. **Measure before and after with
real quotes** — the persona work, the confabulation work and the honesty work were all
driven by held-out probes with real model output, not by how the prompt looked.

### Dry-run before destroying memory
`isha memory --dedupe` previews by default and requires `--apply`. That requirement
immediately earned itself: the first dry-run surfaced a *wrong* merge (two core facts
at 0.885, just over the 0.88 threshold) that would have deleted the fact that her name
is Isha. Never mutate memory without showing what will change.

### Honest ceilings, stated plainly
The memory-grounding ceiling on 3b was reported as a ceiling, not smoothed over. The
persona was rated **6.5/10** rather than declared fixed. Overall progress against the
full vision was put at **35/100**. Keep doing this — an inflated status report costs
more than a disappointing one.

---

## 7. Hardware and constraints

- **Machine:** Intel i5-8300H, 32GB RAM, **NVIDIA GTX 1050 with 4GB VRAM**, Windows 11.
- **The GPU is the bottleneck** and is currently unusable (see §4). Everything runs on
  CPU at ~12 tok/s.
- **Fully local, offline, private, zero cloud cost.** Non-negotiable, and it is the
  identity of the project. A Twilio/VoIP pivot was proposed and **rejected** because it
  would have routed intimate audio through a third party and killed offline operation.
  The three one-time downloads (Ollama model, Piper voice, openWakeWord models) are the
  only network access, and the README says so.
- **Limited personal time.** Prioritise high-impact, low-effort work. Say plainly when
  something is expensive.
- **Goals:** a portfolio and learning project *and* something genuinely used day to day.
  Both matter; neither excuses the other.

---

## 8. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.13 (venv at `.venv`) | 3.11–3.13 supported |
| Reasoning | **Ollama**, `llama3.2` | Was `qwen2.5:3b` (faster, more corporate register). `qwen2.5:7b` grounds better but too slow — see §4 |
| Voice | **Piper** `en_US-amy-medium` | via the `piper-tts` Python API. **GPL-3.0** — see README's licence note; matters only if bundling a binary |
| Hearing | **faster-whisper** `base.en` int8 on **CPU** | CPU on purpose: the GPU is reserved for reasoning |
| Wake word | **openWakeWord** `hey_jarvis` (ONNX) | Placeholder. Models are a runtime download, *not* a pip dependency — rebuild the venv and they vanish; `spike.py` checks for them |
| Memory | **SQLite + sqlite-vec** | facts, episodes, turns, reminders, vectors — one file, `data/isha.db` |
| Embeddings | **fastembed**, `bge-small-en-v1.5`, CPU | never a GPU model; must not contend with the resident LLM |
| Orchestration | custom **asyncio** loop + preemption state machine | deliberately not LangChain: the whole point was controlling the event loop |
| Text UI | stdlib `http.server` + polling, localhost only | no new dependencies, no websockets |

### Layout
```
isha/
  orchestrator.py      the event loop and preemption state machine
  persona.py           SYSTEM_PROMPT + recall_prompt()   <- tune freely, no logic
  context.py           build_messages + the anchoring blocks
  config.py            every default in one place
  factory.py           wires everything from config     <- the swap point
  core/                interfaces.py (contracts), state.py
  audio/               transport, vad, wakeword, calibrate, devices, frames
  stt/                 whisper.py, cleanup.py (wake-prefix stripping)
  tts/                 piper.py, stub.py, sentences.py, speech_text.py
  llm/                 ollama.py, echo.py
  memory/              store, episodes, corpus, temporal, extraction, seed,
                       progress, embedder, forget_parse
  actions/             parse.py (deterministic registry), run.py (does it)
  schedule/            parse, store, scheduler
  ui/                  channel.py, server.py
  smoke.py             the live harness
tests/                 320 tests
spike.py               hardware/plumbing probe
diagnose.py            audio device tools
```

### Commands
```
.venv\Scripts\python.exe -m isha run --device 1 --ollama --ui
.venv\Scripts\python.exe -m isha smoke          # live end-to-end, 7 scenarios, ~2min
.venv\Scripts\python.exe -m pytest -q           # 320 tests, ~2s
.venv\Scripts\python.exe -m isha memory         # inspect stored facts
.venv\Scripts\python.exe -m isha memory --forget "..."
.venv\Scripts\python.exe -m isha memory --dedupe [--apply]
.venv\Scripts\python.exe -m isha seed           # re-apply seeded core/self facts
.venv\Scripts\python.exe -m isha learn <name> <path>   # give her something to read
.venv\Scripts\python.exe -m isha learn --list          # what she has read
.venv\Scripts\python.exe -m isha learn --ask "..."     # what she'd retrieve, + distance
.venv\Scripts\python.exe -m isha say "text"     # test her voice
.venv\Scripts\python.exe -m isha devices        # list mics
.venv\Scripts\python.exe spike.py               # verify the install
```

> Use the venv Python explicitly. Running bare `python` uses system Python, which
> lacks the dependencies; `isha` detects this and says so rather than dumping a
> traceback.

---

## 9. Working style

- **Reasoning before big decisions.** Explain the trade-off and give a recommendation;
  do not silently pick. Design questions (separate table or not, deterministic or LLM)
  get answered *before* code is written.
- **Dry-run and confirm before anything destructive to memory.** Show what will change.
- **Honest ceilings, not oversold progress.** If a model class cannot do better, say
  so plainly. "This is 6.5/10 and here is why" beats "fixed".
- **He tests live and comes back with real transcripts.** Take those seriously — every
  major bug arrived that way. Reproduce before theorising, and say when a reported
  problem turns out to be a test artefact rather than a product bug.
- **Limited time.** Prefer high-impact, low-effort. Flag expensive work as expensive.
- **Commits, progress entries and pushes are automatic**, part of finishing, never
  something to be asked for.
- **Own mistakes plainly and move on.** Several bugs in this project were self-inflicted
  (the persona leaks, the swallowed exception, the extraction gate broken by continuous
  mode). Each was stated plainly, fixed, and pinned with a test.

---

## 10. Where things stand

Against the full vision in §1, this is roughly **55/100** — voice, personality, memory,
episodic memory, timers, always-listening, the text UI, a first real slice of agentic
execution and retrieval over documents he gives her all work; proactive learning,
remote access, the custom voice and voice auth do not exist yet. The agentic slice is
deliberately narrow — it opens, finds and controls, it does not delete or run — and
the knowledge slice answers from what she read at about 5/6, not at expert level.

Against "something worth using every day", it is much further along — closer to 60–70%.
She wakes, listens, remembers, keeps time, admits what she does not know, and can be
talked to or typed at.

The next real step is **proactive daily learning (§5, step 9)** or **remote access
(step 10)**. Cheaper things worth doing first: give the destructive actions (delete,
move, run) the ask-first treatment if they are wanted at all, and add a way to teach
her a new app without editing `config.py`.

**Known rough edges, none blocking:**
- **One-word media commands are STT-flaky.** Piper-spoken "resume" came back as
  "Re-soon." and "skip" as "Skit."; two-word forms ("skip this", "pause the music") are
  reliable. Not a parser bug and not fixable there — fuzzy-matching short words would
  fire on real ones.
- **Cold-start knowledge: 9 of 12 cold questions cost one clarifying turn** ("Are you
  asking about your X?"). Collisions ("my starter motor died") get the same question
  ~3/8 — one word to wave off, never an injection. A declined topic still lingers in
  history for 4 turns, so repeating the collision phrase right after declining can
  retrieve (pre-existing stickiness hole, unchanged).
- **Adding an app means editing `config.py`.** Fine for now, annoying eventually.
- **Wake word is still `hey_jarvis` for BOTH wake and stop.** Parked by choice (§4).
  Whisper sometimes hears it as "8 Jarvis" / "A Jarvis" — the prefix stripper now
  eats those, but expect new spellings; add them to `_FILLER` in `stt/cleanup.py`.
- `.pdf` is not an ingestable format — `.txt`, `.md`, `.markdown`, `.rst` only.

Step 8's **step-by-step guidance mode** ("walk me through it") was deliberately not
built — retrieval answers questions today, and guidance needs multi-turn position
state, which is the dialogue-manager rabbit hole §4 already declined once.
