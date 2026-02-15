# Business Management Lecture Processing Pipeline

> **Purpose:** End-to-end pipeline for processing business management lecture recordings into structured study and revision materials. Mirrors the social work pipeline structure with discipline-specific adaptations.

---

## STAGE 1: Transcript Cleaning

Run this on every Groq Whisper output before any analysis.

---

```
You are a professional academic transcription editor specialising in UK university business and management lectures.

Clean this raw Groq Whisper transcript. Work ONLY with what is in the transcript — do not add, infer, or invent content.

CLEANING RULES:

1. FILLER REMOVAL (selective, not blanket)
   Remove: um, uh, ah, er, "you know" (as filler), "sort of" / "kind of" (as hedging), "basically", "literally" (as emphasis), false starts and repeated phrases.
   KEEP: "okay" or "right" when used as a topic transition marker (e.g., "Right, so if we look at the competitive landscape..."). Remove when used as verbal tics or tag questions ("...right?" at end of sentence seeking agreement).

2. TRANSCRIPTION ERROR CORRECTION
   Fix obvious Whisper errors using surrounding context: homophones (e.g., "their/there"), garbled technical terms, company names, author names, acronyms (e.g., "are oh I" → "ROI", "see sat" → "CSAT", "porter's five forces" not "porters five forces"). If unsure, keep the original and flag as [transcription uncertain: "original text"].

   Common business Whisper errors to watch for:
   - Model/framework names: PESTLE, SWOT, Porter's, Ansoff, BCG
   - Financial terms: EBITDA, ROI, ROE, CAGR, P/E ratio
   - Organisation names: check against context (e.g., "marks and Spencer's" → "Marks & Spencer")
   - Author surnames: Mintzberg, Hofstede, Kaplan, Kotter, Drucker

3. PARAGRAPHING
   Create new paragraphs at topic shifts, not at pauses. Use ## headers ONLY for major section changes (new topic, new case study, new framework, return from break). Do not over-section — a 50-minute lecture should have roughly 4-8 headers, not 20.

4. SPEAKER IDENTIFICATION
   Apply these heuristics (no diarisation available):
   - [Lecturer]: Extended exposition, references to "your reading," "the exam," "when I worked in industry," "the case study shows," pedagogical framing, drawing attention to slides or board
   - [Student]: Shorter utterances, questions ("Sorry, can I ask...," "Does that apply to...," "What about companies that..."), interruptions, personal examples from work experience
   - [Group discussion]: Multiple overlapping voices, workshop/seminar segments, case study group work
   - [Speaker?]: Use when genuinely uncertain — do not guess
   - [Multiple voices]: Use for chaotic segments where individual attribution is impossible

5. UNCLEAR AUDIO
   - Brief gaps: [inaudible: ~2 words] or [inaudible: sounds like "market capitalisation"]
   - Extended gaps (>15 seconds): [inaudible segment: approximately X seconds, topic context: Y]
   - Poor quality sections: [poor audio quality: partial capture] followed by best-effort text in italics

6. PRESERVE EXACTLY AS STATED
   All citations, company names, financial figures, percentages, dates, market data, author references, and proper nouns. Do not "correct" these even if they sound wrong — flag with [sic?] if clearly erroneous (e.g., "Apple's revenue was 50 million" when context suggests billions).

7. NUMERICAL DATA
   Preserve all numbers exactly as spoken. Do not convert between units, round figures, or standardise formats. If the lecturer says "about 23 percent" keep "about 23%" — do not write "23%" or "approximately 23%". The hedging language matters.

8. SPELLING & CONVENTIONS
   UK spelling throughout: behaviour, organisation, centre, defence, programme, analyse, favour, labour.
   UK business conventions: "turnover" not "revenue" if that's what was said, "plc" not "PLC", "Ltd" conventions.

9. TIMESTAMPS
   Remove all timestamp clutter. Only retain a timestamp if it marks a structurally important moment (e.g., start of a case study discussion, return from break, start of group activity): [00:32:15 — Case study: Tesco begins].

OUTPUT FORMAT:
- Markdown with ## headers for major sections only
- Paragraphs for exposition, bullet points only for actual lists spoken as lists
- Chronological order maintained
- No summary, no analysis, no commentary — clean transcript only

TRANSCRIPT:
[paste raw Whisper output here]
```

---

## STAGE 2: Analysis Approaches

Choose ONE approach per transcript based on module and purpose.

**Critical rule for all approaches:** Work ONLY from the cleaned transcript. Every claim, quote, reference, data point, and figure must be traceable to something actually said. If you are uncertain whether something was stated, flag it with [uncertain — verify against recording]. Never fabricate citations, statistics, company data, or framework applications.

---

### Approach A: Strategic Case Bank

**Best for:** Strategy, marketing, organisational behaviour, operations, international business modules

```
You are a UK business school academic assistant. Transform this cleaned lecture transcript into a structured strategic study guide.

GROUNDING RULE: Every entry below must come from the transcript. Do not supplement with your own knowledge of companies, industries, or frameworks. If the lecturer named a model but didn't fully explain it, note what was said and flag gaps. If a company or case was mentioned but not developed, list it under "Brief Mentions" rather than constructing analysis around it.

OUTPUT STRUCTURE (Markdown):

## Models & Frameworks Applied
| Model / Framework | How It Was Used | Case / Example | Lecturer's Critique or Caveat | Verbatim or Paraphrased? |
|-------------------|-----------------|----------------|-------------------------------|--------------------------|
| e.g., Porter's Five Forces | Applied to UK grocery sector | Tesco vs. Aldi | "Porter doesn't account for digital disruption" | Paraphrased |

Only include frameworks the lecturer explicitly named or applied. If a model was alluded to but not named (e.g., describing competitive forces without saying "Porter"), list under "Possible Framework References" with context clues.

Note: Where the lecturer critiqued or qualified a model, capture this — it's often the most valuable material for essays.

## Data & Figures Cited
| Figure | Context | Source (if stated) | How It Was Used |
|--------|---------|-------------------|-----------------|
| e.g., "about 23% market share" | Tesco's position in 2023 | "From the Kantar data" | Evidence for market dominance argument |

Do not round, adjust, or "correct" figures — record exactly as stated including hedging language ("about," "roughly," "something like"). Flag any figure that sounds implausible with [sic?].

## Case Studies Discussed
For each company or organisation discussed substantively (more than a passing mention):
- **Organisation**: [Name]
- **Context**: [Market position, sector, situation as described]
- **Strategic challenge**: [The problem or decision discussed]
- **Framework applied**: [Theory or model the lecturer used — or "none explicitly applied"]
- **Key decisions / actions**: [What the company did or should have done — as discussed]
- **Outcome or lesson**: [What the lecturer concluded]
- **Gaps or limitations**: [Anything the lecturer flagged as incomplete, debatable, or oversimplified]
- **Assessment angle**: [How this case could be used in an essay or exam — based on how the lecturer framed it]

## Brief Mentions
Companies or examples referenced in passing without substantial analysis:
- **Name**: [Context of mention — e.g., "used as a contrast to Tesco's approach"]

## Debates & Contested Positions
Where the lecturer presented competing viewpoints or acknowledged disagreement:
- **Debate**: [e.g., shareholder primacy vs. stakeholder theory]
- **Position A**: [Argument and evidence as presented]
- **Position B**: [Argument and evidence as presented]
- **Lecturer's lean**: [Did they signal a preference? How? Quote if possible. If neutral, say so.]
- **Useful tension for essays**: [Why this debate is valuable — as framed in the lecture]

## Definitions & Terminology
Record technical terms with the lecturer's own wording:
- **Term**: [Definition as given — not a textbook definition]
- **Context**: [How it was introduced or what example accompanied it]
- **Textbook contrast**: [If the lecturer distinguished their definition from the textbook, capture both]

## Stakeholder & Industry Analysis
Where the lecturer discussed stakeholder dynamics, industry structure, or competitive positioning:
- **Stakeholder / Actor**: [Who]
- **Interest**: [What they want — as described]
- **Power / Influence**: [As characterised by the lecturer]
- **Strategic implication**: [What this means for the firm discussed]

Only include if explicitly discussed. Do not construct stakeholder maps from implication.

## Cause-and-Effect Chains
Where the lecturer walked through a logical sequence (e.g., "if interest rates rise, then consumer spending falls, which means..."):
- **Chain**: [Step 1] → [Step 2] → [Step 3] → [Conclusion]
- **Context**: [What triggered this explanation]
- **Assessment value**: [These chains are gold for exam answers — note if the lecturer flagged this]

## References Mentioned
Recover reading references using context clues:
- **Clue from lecture**: [e.g., "as Mintzberg argues in the chapter on...," "the HBR case we looked at last week"]
- **Likely source**: [Best guess with reasoning]
- **Key argument attributed**: [What the lecturer said about it]
- **Confidence**: High / Medium / Low

## Workplace & Placement Application
- **Immediate applicability**: [Concepts or frameworks that could be applied in a current or recent work context]
- **Interview / assessment centre relevance**: [Models or cases useful for graduate scheme applications — e.g., "being able to apply PESTLE in a case study interview"]
- **Professional development**: [Analytical skills or perspectives worth practising]

Frame as practical actions, not "the lecture said..."

## Seminar & Tutorial Preparation
Generate 3 discussion questions that surface genuine tensions in the material. Frame as "To what extent..." or "How should firms balance..." — not simple recall. Examples of good tension areas:
- Short-term profit vs. long-term sustainability
- First-mover advantage vs. fast follower strategy
- Quantitative metrics vs. qualitative strategic judgement
- Global standardisation vs. local adaptation
- Shareholder value vs. broader stakeholder responsibility

## Emphasis Coding
Rate by observable lecturer behaviour:
- 🔴 HIGH: Repeated 3+ times, voice emphasis, explicit exam/assessment flagging ("you need to know this," "this will come up," "I guarantee there'll be a question on...")
- 🟡 MEDIUM: Explained clearly with examples, given significant lecture time
- 🟢 LOW: Mentioned in passing, tangential, responded to student question without elaboration

List each key point with its code.

FORMAT: Professional UK academic English. Markdown.
```

---

### Approach B: Assessment-Focused Revision Guide

**Best for:** Exam preparation, assignment planning, targeted revision

```
Analyse this cleaned lecture transcript for assessment relevance. Produce a revision-focused guide for a UK business management student.

GROUNDING RULE: All content must come from the transcript. Quotes must be flagged as approximate (they've been through Whisper transcription and cleaning — they are not truly verbatim). Do not invent exam questions on topics not covered in this lecture.

## Assessment Type (Best Guess)
Based on content weighting, tick the most likely format:
- [ ] Case study exam (narrative scenarios requiring framework application)
- [ ] Essay exam (debate-driven, "critically evaluate" questions)
- [ ] MCQ / short answer (definition-heavy, factual recall)
- [ ] Report-style assessment (applied analysis of a real company or industry)
- [ ] Presentation / group work (collaborative analysis, stakeholder engagement)
- [ ] Mixed/unclear — explain why

## Quotable Passages
Extract up to 5 passages suitable for academic use:
- **Passage**: "[Text as cleaned — not original verbatim]"
- **Context**: [Topic and why it was said]
- **Reliability**: [Was this clearly stated, or reconstructed from poor audio?]
- **Suggested use**: [Introduction / Evidence / Counterargument / Conclusion]

⚠️ These passages have been through speech-to-text and cleaning. They are approximate. Verify against the recording before using in assessed work, or cite as "Lecture, [Module], [Date], paraphrased from recording."

## Models, Cases & References Cited
| Name / Title | What Was Said About It | Potential Use in Assessment |
|-------------|------------------------|----------------------------|
| [Framework, company, or author] | [Key point attributed] | [Which section of an essay/exam] |

## Theory-to-Practice Translation
For each theoretical concept discussed:
- **Theory**: [As stated in lecture]
- **Practical meaning**: [What a manager or analyst should actually do with this]
- **Risk if ignored**: [Consequence the lecturer identified — commercial, strategic, or reputational]
- **Example given**: [The real-world case used to illustrate, if any]

## Emphasis Coding
Rate by observable lecturer behaviour:
- 🔴 HIGH: Repeated 3+ times, voice emphasis, explicit exam/assessment flagging
- 🟡 MEDIUM: Explained clearly with examples, given time
- 🟢 LOW: Mentioned in passing, tangential, responded to student question without elaboration

List each key point with its code.

## Practice Questions
Generate from lecture content only:
- 2 essay-style questions (using "Critically evaluate..." or "To what extent..." format)
- 3 short-answer factual questions (testable facts from the lecture)
- 1 case-study question (using a company or scenario discussed in the lecture, requiring framework application)

## Diagram & Model Recreation
For any model or framework the lecturer drew, described drawing, or referenced visually:
- **Model**: [Name]
- **Components**: [What goes where — as described]
- **How to sketch**: [Step-by-step recreation instructions for exam conditions]
- **Common mistakes**: [If the lecturer flagged errors students typically make]

## Reading List Recovery
| Clue from Lecture | Likely Source | Confidence | Priority |
|-------------------|--------------|------------|----------|
| "the HBR article on disruption" | [Best guess] | Medium | Essential |

FORMAT: UK academic English. Markdown.
```

---

### Approach C: Annotated Study Guide

**Best for:** Active revision, printing, handwritten annotation, visual learners

```
Convert this cleaned lecture transcript into an annotated study guide designed for printing and handwritten notes. This is for a UK business management student.

FORMAT: Use the following structure for each topic section. Do NOT use markdown tables for the main content — they break when content is longer than a few words.

---

## [Topic Header]

[Clean lecture content in paragraphs. **Bold** key terms, definitions, and company names. Use bullet points only for content that was delivered as a list.]

> 📖 THEORY LINK: [Connect to a reading or framework — only if one was mentioned or clearly implied in the lecture]
> 🏢 REAL-WORLD EXAMPLE: [Company or case study connected to this point — as discussed]
> 🔧 APPLICATION: [How this applies to work, a placement, or an assignment]
> ❓ CHECK: Can I explain this concept without notes? Can I apply the framework to a new company? [Y/N — leave blank for student to fill]
> 💭 THINK FURTHER: [One question that pushes beyond the lecture content — e.g., "What happens to this model in a digital-first market?"]

---

Repeat for each section.

END MATTER:

## Key Terms
5-7 terms with definitions drawn from the lecture (not textbook definitions):
- **Term**: [Definition as the lecturer explained it]

## Framework Quick-Reference
For each model discussed, a minimal sketch description:
- **Model**: [Name] — [Components in ≤15 words] — [When to use it]

## Three Takeaways
Three single-sentence summaries of the most important points.

## Exam Alert
The single most emphasised point in the lecture (repeated, stressed, or explicitly flagged for assessment).

## Confusion Flags
List any concepts that were unclear in the transcript (poor audio, incomplete explanation, contradictory statements):
- [Concept]: [What was unclear and why] — suggest: [action to resolve, e.g., "check textbook chapter X," "ask in seminar," "compare with lecture notes from week Y"]

FORMAT: Must paste cleanly into Word. No nested tables. Print-friendly on A4.
```

---

## STAGE 3: Optional Add-ons

---

### One-Page Cheat Sheet

Run AFTER Stage 2 analysis is complete. Input = the analysis output.

```
Create a one-page A4 revision cheat sheet from this business lecture analysis. Aim for maximum information density — this is a revision aid, not a summary.

LAYOUT: Single markdown table, 2 columns, designed for A4 portrait printing.

| KEY CONCEPTS | FRAMEWORKS & APPLICATION |
|---|---|
| **Terms** | **Models** |
| [Term 1]: [≤10 word definition] | [Framework 1]: [Core principle in ≤15 words] |
| [Term 2]: [≤10 word definition] | [Framework 2]: [Core principle in ≤15 words] |
| [Term 3]: [≤10 word definition] | [Framework 3]: [Core principle in ≤15 words] |
| [Term 4]: [≤10 word definition] | |
| [Term 5]: [≤10 word definition] | **Key Data** |
| | [Stat/figure 1 with context] |
| **📊 CASE STUDY ESSENTIALS** | [Stat/figure 2 with context] |
| [Company 1]: [Strategic lesson | [Stat/figure 3 with context] |
| in ≤15 words] | |
| [Company 2]: [Strategic lesson | **📝 LIKELY QUESTION** |
| in ≤15 words] | [Predicted exam question in |
| | ≤20 words] |
| **⚠️ MUST KNOW** | |
| [Single most emphasised point — | **🔗 KEY READING** |
| the one thing to learn if you | [Most important reference |
| learn nothing else] | mentioned, with context] |
| | |
| **🔄 KEY DEBATE** | **✏️ DIAGRAM TO PRACTISE** |
| [Central tension or contested | [Model name + what to |
| position in ≤25 words — the | sketch from memory] |
| kind of thing that becomes an | |
| essay question] | |

RULES:
- Everything must fit one A4 page when pasted into Word (12pt, standard margins)
- No full sentences — fragments, abbreviations, and shorthand are fine
- Every item must come from the Stage 2 analysis — do not add new content
- If there isn't enough content for a cell, leave it as "—" rather than inventing
```

---

### Context Header (for automation)

Prepend this to Stage 1 if you have module metadata available:

```
CONTEXT FOR THIS RECORDING:
Module: [Code and name, e.g., BUS2040 Strategic Management]
Week: [Number]
Lecture topic: [From timetable or VLE]
Required reading: [From module handbook — textbook chapters, HBR cases, journal articles]
Assessment this feeds: [Which assignment, with deadline if known — e.g., "Group report on competitive analysis, due Week 12"]
Learning outcomes: [Relevant LOs from module spec]

USE THIS CONTEXT TO:
- Flag content that directly addresses a stated learning outcome: "⚡ This directly addresses LO[X]"
- Connect vague reading references to likely items on the reading list
- Note assessment-relevant emphasis: "📝 Assessment-relevant: connects to [assignment name]"
- Identify which framework applications are likely expected in the assessment
- Do NOT let context override what was actually said — if the lecture diverges from the stated topic, note the divergence rather than forcing alignment
```

---

### Quality Assurance Pass (recommended)

Run this after any Stage 2 output to catch errors:

```
Review this business lecture analysis for quality. Check each item against the original cleaned transcript.

FLAG:
1. Any claim, statistic, company data, market figure, or citation that does not appear in the transcript → mark as [NOT IN TRANSCRIPT — remove or verify]
2. Any framework application, stakeholder mapping, or industry analysis that was constructed by the analyst rather than stated by the lecturer → mark as [ANALYST ADDITION — verify appropriateness]
3. Any quote marked as "verbatim" that has been altered during cleaning → downgrade to "approximate"
4. Any practice question that tests content not covered in this lecture → mark as [OUT OF SCOPE]
5. Any reading reference marked "High confidence" without strong evidence (e.g., specific author + title mentioned) → downgrade to Medium or Low
6. Any company data that has been rounded, adjusted, or standardised from what was actually stated → restore original phrasing
7. Any framework critique or limitation attributed to the lecturer that was actually added by the analyst → mark as [ANALYST ADDITION]

Output the analysis with corrections applied and a brief summary of changes made.
```

---

## Pipeline Order

```
Stage 1 (Clean)
    → Save as Clean_Transcript.md or .docx
    ↓
Stage 2 (Choose A, B, or C)
    → Save as Analysis.md or .docx
    ↓
Stage 3a (QA Pass — recommended)
    → Verify analysis against transcript
    ↓
Stage 3b (Cheat Sheet — optional)
    → Save as CheatSheet.md or .docx
```

Or combine into one document with clear section breaks:
```
# PART 1: Clean Transcript
[Stage 1 output]

---

# PART 2: Analysis
[Stage 2 output]

---

# PART 3: Quick Reference
[Stage 3 output]
```

---

## Changelog (vs. social work pipeline)

| Change | Reason |
|--------|--------|
| Stage 1 adapted for business terminology | Whisper commonly garbles financial acronyms, company names, and framework names differently to social work terms |
| Added common Whisper error watchlist for business | ROI, EBITDA, CAGR, PESTLE etc. are frequently mangled |
| Added numerical data preservation rule | Business lectures are data-heavy; hedging language ("about 23%") carries analytical meaning |
| Replaced Statutory Frameworks with Models & Frameworks | Equivalent structural role but discipline-appropriate |
| Replaced PCF domain mapping with stakeholder analysis | Business equivalent of the professional framework mapping |
| Replaced Anti-Oppressive Practice with Debates & Contested Positions | Captures the critical analysis dimension relevant to business |
| Added Cause-and-Effect Chains section (Approach A) | Business lecturers frequently walk through causal logic; these chains are high-value exam material |
| Added Brief Mentions section (Approach A) | Business lectures often name-drop companies without analysis; separating these prevents over-interpretation |
| Added Diagram & Model Recreation section (Approach B) | Business exams frequently require sketching frameworks from memory |
| Added Case Study Essentials to cheat sheet | Business revision needs quick-reference company examples more than social work does |
| QA pass includes company data verification | Prevents rounding or adjusting financial figures that were stated with specific hedging |
| Workplace application includes interview/assessment centre relevance | Business students need frameworks for graduate recruitment as well as academic assessment |
