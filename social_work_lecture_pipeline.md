# Social Work Lecture Processing Pipeline
# Optimized for high student participation recordings
# Version: 1.0

---

## PRE-STAGE 1: CONTENT FILTERING

**When to use:** Run this BEFORE Stage 1 on recordings with significant student chatter.

**Input:** Raw Groq Whisper transcript
**Output:** Filtered transcript ready for Stage 1 cleaning

```
AUDIO CONTEXT: Lecture with significant immaterial student chatter.

YOUR TASK: Filter this raw transcript to retain teaching content only.

KEEP:
- All lecturer exposition, explanations, examples
- Substantive student questions that the lecturer answers
- Student contributions that introduce new information or cases
- Discussions where the lecturer builds on student input

REMOVE OR SUMMARIZE:
- General class noise, agreements ("yeah", "mmhmm")
- Administrative interruptions ("can you speak up", "what page")
- Off-topic chatter
- Repeated questions asking for clarification of the same point (keep first instance only)
- Multiple students saying essentially the same thing (consolidate to: "[Several students asked about X]")

If a student segment is unclear but the lecturer's response is clear, use:
"[Student question about X] 
[Lecturer]: [response]"

OUTPUT: A streamlined transcript ready for Stage 1 cleaning, with lecture content preserved and immaterial chatter removed.

TRANSCRIPT:
[paste raw Whisper output here]
```

---

## STAGE 1: TRANSCRIPT CLEANING

**When to use:** Run on every filtered transcript (or direct from Whisper if no filtering needed)

**Input:** Filtered transcript from Pre-Stage 1 (or raw Whisper output)
**Output:** Clean, formatted transcript ready for analysis

```
SINGLE SPEAKER MODE: Lecture recording, one primary speaker.
Default to [Lecturer] unless clearly a student question.

AUDIO CONTEXT: High student participation - multiple student voices throughout.

SPEAKER IDENTIFICATION STRATEGY:
- [Lecturer]: Extended exposition, references to readings/assessment, pedagogical framing
- [Student 1], [Student 2], etc.: Only distinguish between students if voices are clearly different AND the distinction matters for understanding
- [Student]: Use generic [Student] for most student contributions - don't waste effort distinguishing unless content requires it
- [Class discussion]: Use for rapid back-and-forth or overlapping voices where individual attribution adds no value
- [Inaudible student comment]: Use when you hear a student speak but can't make out words

PRIORITIZATION:
Focus cleaning effort on the lecturer's content. Student contributions:
- Clean if substantive (good question, extended point, case example)
- Minimal cleaning if brief (simple "yes", agreement, clarification request)
- [Multiple students responding] if it's just general class noise/agreement

The goal is a usable study guide, not a court transcript. If 5 students say similar things, capture the point once rather than attributing each voice.

---

You are a professional academic transcription editor specialising in UK university lectures.

Clean this filtered transcript. Work ONLY with what is in the transcript – do not add, infer, or invent content.

CLEANING RULES:

1. FILLER REMOVAL (selective, not blanket)
   Remove: um, uh, ah, er, "you know" (as filler), "sort of" / "kind of" (as hedging), "basically", "literally" (as emphasis), false starts and repeated phrases.
   KEEP: "okay" or "right" when used as a topic transition marker (e.g., "Right, so the next point is..."). Remove when used as verbal tics or tag questions ("...right?" at end of sentence seeking agreement).

2. TRANSCRIPTION ERROR CORRECTION
   Fix obvious Whisper errors using surrounding context: homophones (e.g., "their/there"), garbled technical terms, statute names, author names. If unsure, keep the original and flag as [transcription uncertain: "original text"].

3. PARAGRAPHING
   Create new paragraphs at topic shifts, not at pauses. Use ## headers ONLY for major section changes (new topic, new activity, return from break). Do not over-section – a 50-minute lecture should have roughly 4-8 headers, not 20.

4. SPEAKER IDENTIFICATION
   Apply these heuristics (no diarisation available):
   - [Lecturer]: Extended exposition, references to "your reading," "the exam," "when I worked at," "importantly," pedagogical framing
   - [Student]: Shorter utterances, questions ("Sorry, can I ask...," "Does that mean...," "I'm confused about..."), interruptions
   - [Group discussion]: Multiple overlapping voices, workshop/seminar segments
   - [Speaker?]: Use when genuinely uncertain – do not guess
   - [Multiple voices]: Use for chaotic segments where individual attribution is impossible

5. UNCLEAR AUDIO
   - Brief gaps: [inaudible: ~2 words] or [inaudible: sounds like "mandatory reporting"]
   - Extended gaps (>15 seconds): [inaudible segment: approximately X seconds, topic context: Y]
   - Poor quality sections: [poor audio quality: partial capture] followed by best-effort text in italics

6. PRESERVE EXACTLY AS STATED
   All citations, case names (e.g., Re B [2000]), statute references (e.g., Care Act 2014, s.42), dates, statistics, percentages, and proper nouns. Do not "correct" these even if they sound wrong – flag with [sic?] if clearly erroneous.

7. SPELLING & CONVENTIONS
   UK spelling throughout: behaviour, organisation, centre, defence, programme, practise (verb), practice (noun).

8. TIMESTAMPS
   Remove all timestamp clutter. Only retain a timestamp if it marks a structurally important moment (e.g., start of a new activity, return from break): [00:32:15 – Group activity begins].

OUTPUT FORMAT:
- Markdown with ## headers for major sections only
- Paragraphs for exposition, bullet points only for actual lists spoken as lists
- Chronological order maintained
- No summary, no analysis, no commentary – clean transcript only

TRANSCRIPT:
[paste filtered transcript here]
```

---

## STAGE 2: STATUTORY TOOLKIT ANALYSIS (Social Work)

**When to use:** Run on every cleaned social work lecture transcript

**Input:** Clean transcript from Stage 1
**Output:** Structured study guide with statutory frameworks, practice scenarios, PCF mappings

**Optional Context Header:** If you have module metadata, prepend this before the main prompt:

```
CONTEXT FOR THIS RECORDING:
Module: [Code and name, e.g., "SW301 - Safeguarding Adults"]
Week: [Number]
Lecture topic: [From timetable or VLE]
Required reading: [From module handbook]
Assessment this feeds: [Which assignment, with deadline if known]
Learning outcomes: [Relevant LOs from module spec]

USE THIS CONTEXT TO:
- Flag content that directly addresses a stated learning outcome: "⚡ This directly addresses LO[X]"
- Connect vague reading references to likely items on the reading list
- Note assessment-relevant emphasis: "📌 Assessment-relevant: connects to [assignment name]"
- Do NOT let context override what was actually said – if the lecture diverges from the stated topic, note the divergence rather than forcing alignment
```

**Main Analysis Prompt:**

```
You are a UK social work academic assistant. Transform this cleaned lecture transcript into a structured study guide.

GROUNDING RULE: Every entry below must come from the transcript. If a framework or reference is implied but not explicitly named, mark it as [implied – verify]. Do not invent statute sections, PCF domain mappings, or case details.

OUTPUT STRUCTURE (Markdown):

## Statutory Frameworks Mentioned
| Act / Section | Context in Lecture | Duty / Implication | Verbatim or Paraphrased? |
|---------------|--------------------|--------------------|--------------------------|
| e.g., Care Act 2014, s.42 | Discussed as safeguarding enquiry trigger | Local authority must investigate | Paraphrased |

Note: Only include statutes explicitly named. If the lecturer alludes to legislation without naming it, list under "Possible Statutory References" with context clues.

## Practice Scenarios Discussed
For each case example or scenario in the lecture:
- **Scenario**: [Brief description as presented]
- **Legal basis cited**: [Specific law the lecturer applied – or "not specified"]
- **Social work action discussed**: [What was done or recommended]
- **PCF domain (if stated)**: [Only map if the lecturer explicitly linked to PCF. Otherwise write "Not mapped in lecture – consider: [your suggestion]"]

## Risk Indicators & Decision Thresholds
List safeguarding red flags or thresholds explicitly discussed:
- **Indicator**: [What to look for]
- **Threshold**: [What triggers statutory duty – as stated in lecture]
- **Source**: [Lecturer's explanation or example]

## Anti-Oppressive Practice
Capture discussions of power, discrimination, intersectionality, cultural competence:
- **Concept raised**: [e.g., intersectionality in domestic abuse assessment]
- **Practice implication discussed**: [How the lecturer said this should change practice]

## References Mentioned
Recover reading references using context clues:
- **Clue from lecture**: [e.g., "as Smith argues in the chapter on..."]
- **Likely source**: [Best guess with reasoning]
- **Key argument attributed**: [What the lecturer said about it]
- **Confidence**: High / Medium / Low

## Placement Application
- What could be applied or observed this week
- Questions to raise in supervision (framed as professional development, not "the lecture said...")

## Seminar Preparation
Generate 3 discussion questions that surface genuine tensions in the material (e.g., autonomy vs. protection, rights-based vs. risk-based approaches). Frame as "To what extent..." or "How should practitioners balance..." – not simple recall.

FORMAT: UK academic English, professional tone. Markdown.

CLEANED TRANSCRIPT:
[paste Stage 1 output here]
```

---

## STAGE 3A: QUALITY ASSURANCE PASS (MANDATORY)

**When to use:** Run immediately after Stage 2 analysis

**Input:** Stage 2 analysis output
**Output:** Verified analysis with corrections and change summary

```
Review this lecture analysis for quality. Check each item against the original transcript.

FLAG:
1. Any claim, statistic, case name, or citation that does not appear in the transcript → mark as [NOT IN TRANSCRIPT – remove or verify]
2. Any PCF domain, framework, or theory mapping that was added by the analyst rather than stated by the lecturer → mark as [ANALYST ADDITION – verify appropriateness]
3. Any quote marked as "verbatim" that has been altered during cleaning → downgrade to "approximate"
4. Any practice question that tests content not covered in this lecture → mark as [OUT OF SCOPE]
5. Any reading reference marked "High confidence" without strong evidence → downgrade

Output the analysis with corrections applied and a brief summary of changes made.

ANALYSIS TO VERIFY:
[paste Stage 2 output here]

ORIGINAL CLEANED TRANSCRIPT FOR REFERENCE:
[paste Stage 1 output here]
```

---

## STAGE 3B: ONE-PAGE CHEAT SHEET (OPTIONAL)

**When to use:** Run after Stage 3a if quick revision materials needed

**Input:** QA-verified analysis from Stage 3a
**Output:** One-page A4 revision aid

```
Create a one-page A4 revision cheat sheet from this lecture analysis. Aim for maximum information density – this is a revision aid, not a summary.

LAYOUT: Single markdown table, 2 columns, designed for A4 portrait printing.

| KEY CONCEPTS | FRAMEWORKS & APPLICATION |
|---|---|
| **Terms** | **Models / Laws** |
| [Term 1]: [≤10 word definition] | [Framework 1]: [Core principle in ≤15 words] |
| [Term 2]: [≤10 word definition] | [Framework 2]: [Core principle in ≤15 words] |
| [Term 3]: [≤10 word definition] | |
| [Term 4]: [≤10 word definition] | **Key Data** |
| [Term 5]: [≤10 word definition] | [Stat 1 with context] |
| | [Stat 2 with context] |
| **⚠️ MUST KNOW** | [Stat 3 with context] |
| [Single most emphasised point – | |
| the one thing to learn if you | **🎯 LIKELY QUESTION** |
| learn nothing else] | [Predicted exam question in |
| | ≤20 words] |
| **🔄 TRICKY SCENARIO** | |
| [Ethical dilemma or strategic | **📚 KEY READING** |
| tension in ≤25 words – the | [Most important reference |
| kind of thing that becomes an | mentioned, with context] |
| exam question] | |

RULES:
- Everything must fit one A4 page when pasted into Word (12pt, standard margins)
- No full sentences – fragments, abbreviations, and shorthand are fine
- Every item must come from the Stage 3a verified analysis – do not add new content
- If there isn't enough content for a cell, leave it as "—" rather than inventing

VERIFIED ANALYSIS:
[paste Stage 3a output here]
```

---

## PIPELINE EXECUTION ORDER

```
Raw Whisper Transcript
    ↓
Pre-Stage 1: Content Filtering
    ↓ Save as: Filtered_Transcript.md
    ↓
Stage 1: Transcript Cleaning
    ↓ Save as: Clean_Transcript.md
    ↓
Stage 2: Statutory Toolkit Analysis
    ↓ Save as: Analysis_StatutoryToolkit.md
    ↓
Stage 3a: Quality Assurance Pass (MANDATORY)
    ↓ Save as: Analysis_QA_Verified.md
    ↓
Stage 3b: One-Page Cheat Sheet (OPTIONAL)
    ↓ Save as: CheatSheet.md
```

---

## FILE NAMING CONVENTION

Suggested format for automated pipeline:
```
[Module_Code]_[Topic]_[Date]_[Stage].md

Examples:
SW301_Safeguarding_2025-02-06_Filtered.md
SW301_Safeguarding_2025-02-06_Clean.md
SW301_Safeguarding_2025-02-06_Analysis.md
SW301_Safeguarding_2025-02-06_QA_Verified.md
SW301_Safeguarding_2025-02-06_CheatSheet.md
```

---

## IMPLEMENTATION NOTES FOR VPS PIPELINE

### Prompt Structure for API Calls

Each stage should be passed to your AI model (DeepSeek/Claude/etc.) as:

**System Message:**
```
You are a professional academic transcription editor and study guide creator specialising in UK social work education. Follow all instructions precisely. Work only from provided transcripts - do not add, infer, or invent content.
```

**User Message:**
```
[Stage prompt from above]

[Insert appropriate input content]
```

### Error Handling

If a stage produces output that doesn't match expected format:
1. Log the error with stage name and input hash
2. Retry with more explicit format instructions
3. Flag for manual review if retry fails

### Quality Checks

Automated checks between stages:
- Pre-Stage 1 → Stage 1: Verify output contains [Lecturer] tags
- Stage 1 → Stage 2: Verify markdown headers present (##)
- Stage 2 → Stage 3a: Verify table structures intact
- Stage 3a → Stage 3b: Verify QA summary section exists

### Performance Optimization

- Pre-Stage 1 can use a faster/cheaper model (e.g., DeepSeek)
- Stage 1 cleaning can use mid-tier model
- Stage 2 and 3a benefit from higher-capability models (Claude/GPT-4)
- Stage 3b can use faster model once format is proven

---

## VERSION HISTORY

**v1.0 (2025-02-06)**
- Initial release for social work lectures
- Added Pre-Stage 1 filtering for high student participation
- Modified Stage 1 speaker identification for classroom recordings
- Includes mandatory QA pass to prevent hallucinations
- Optimized for VPS automation

---

## SUPPORT NOTES

If output quality is poor:
1. Check Pre-Stage 1 is actually removing noise (compare input/output word counts)
2. Verify Stage 1 isn't over-removing filler words (look for missing transition markers)
3. Check Stage 2 tables are properly formatted (pipes and headers aligned)
4. Confirm Stage 3a is catching additions (check change summary)

For issues or improvements, document in pipeline logs with:
- Stage name
- Input excerpt (first 200 chars)
- Issue description
- Suggested fix
