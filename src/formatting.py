"""
Transcript formatting module using DeepSeek API.

This module provides the DeepSeekFormatter class for formatting raw transcripts
into structured markdown notes based on note type (meeting, supervision, client, etc.)
"""

import logging
import time
from typing import Optional, Dict, List, Callable
from dataclasses import dataclass

# Configure logging
logger = logging.getLogger(__name__)


class FormattingError(Exception):
    """Custom exception for transcript formatting errors."""
    pass


# Note-type specific prompts
MEETING_PROMPT = """
Format this meeting transcript with the following sections:
- Attendees: List of people present
- Date/Time: If mentioned
- Discussion Summary: Bullet points of key topics discussed
- Decisions Made: Numbered list of decisions
- Action Items: Numbered list with assignees and due dates if mentioned
- Next Steps: Any follow-up meetings or actions

Raw transcript:
{transcript}
"""

SUPERVISION_PROMPT = """
Format this clinical supervision transcript with:
- Participants: Supervisor and supervisee names if mentioned
- Cases Discussed: List with brief context (anonymized)
- Interventions/Techniques: Methods discussed
- Learning Points: Key clinical insights
- Goals/Action Items: Professional development goals
- Risk Considerations: Any risk-related discussions

Raw transcript:
{transcript}
"""

CLIENT_PROMPT = """
Format this therapy session transcript with:
- Session Type: Individual/Couple/Family if clear
- Presenting Issues: Client concerns (anonymized)
- Interventions Used: Therapeutic techniques applied
- Client Progress: Changes since last session
- Risk Assessment: Any safety concerns
- Homework/Tasks: Assigned between sessions
- Plan for Next Session

Raw transcript:
{transcript}
"""

LECTURE_PROMPT = """
Format this lecture transcript with:
- Title/Topic: Main subject
- Lecturer: Name if mentioned
- Sections: Major topics with timestamps if available
- Key Concepts: Important definitions/explanations
- Summary: Brief overview
- Questions/Discussion Points

Raw transcript:
{transcript}
"""

BRAINDUMP_PROMPT = """
Format this voice note/braindump with:
- To-Do Items: Actionable tasks extracted
- Ideas: Creative thoughts or concepts
- Mind Map: Generate in Mermaid format showing connections between ideas
- Categories: Group related thoughts

Raw transcript:
{transcript}
"""

# Mapping of note types to prompts
PROMPT_TEMPLATES = {
    "MEETING": MEETING_PROMPT,
    "SUPERVISION": SUPERVISION_PROMPT,
    "CLIENT": CLIENT_PROMPT,
    "LECTURE": LECTURE_PROMPT,
    "BRAINDUMP": BRAINDUMP_PROMPT,
}


# ============================================================================
# SOCIAL WORK LECTURE PIPELINE PROMPTS (Kate)
# ============================================================================

SOCIAL_WORK_PRE_STAGE_1 = """AUDIO CONTEXT: Lecture with significant immaterial student chatter.

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
{transcript}"""

SOCIAL_WORK_STAGE_1 = """SINGLE SPEAKER MODE: Lecture recording, one primary speaker.
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
{transcript}"""

SOCIAL_WORK_STAGE_2 = """You are a UK social work academic assistant. Transform this cleaned lecture transcript into a structured study guide.

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
{transcript}"""

SOCIAL_WORK_STAGE_3A = """Review this lecture analysis for quality. Check each item against the original transcript.

FLAG:
1. Any claim, statistic, case name, or citation that does not appear in the transcript → mark as [NOT IN TRANSCRIPT – remove or verify]
2. Any PCF domain, framework, or theory mapping that was added by the analyst rather than stated by the lecturer → mark as [ANALYST ADDITION – verify appropriateness]
3. Any quote marked as "verbatim" that has been altered during cleaning → downgrade to "approximate"
4. Any practice question that tests content not covered in this lecture → mark as [OUT OF SCOPE]
5. Any reading reference marked "High confidence" without strong evidence → downgrade

Output the analysis with corrections applied and a brief summary of changes made.

ANALYSIS TO VERIFY:
{transcript}

ORIGINAL CLEANED TRANSCRIPT FOR REFERENCE:
{cleaned_transcript}"""

SOCIAL_WORK_STAGE_3B = """Create a one-page A4 revision cheat sheet from this lecture analysis. Aim for maximum information density – this is a revision aid, not a summary.

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
{transcript}"""


@dataclass
class ProcessingStage:
    """Defines a single stage in a multi-stage processing pipeline."""
    name: str
    prompt_template: str
    system_message: str
    model: str = "deepseek-chat"
    temperature: float = 0.3
    max_tokens: int = 4096
    timeout: int = 120
    requires_previous: bool = True  # Whether this stage needs previous stage output
    save_intermediate: bool = True  # Whether to save this stage's output
    filename_suffix: str = ""  # Suffix for intermediate file (e.g., "_filtered", "_clean")


# ============================================================================
# BUSINESS LECTURE PIPELINE PROMPTS (Keira)
# ============================================================================

BUSINESS_STAGE_1 = """You are a professional academic transcription editor specialising in UK university business and management lectures.

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
   - [Student]: Shorter utterances, questions ("Sorry, can I ask..., " "Does that apply to..., " "What about companies that..."), interruptions, personal examples from work experience
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
{transcript}"""

BUSINESS_STAGE_2A = """You are a UK business school academic assistant. Transform this cleaned lecture transcript into a structured strategic study guide.

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
- **Clue from lecture**: [e.g., "as Mintzberg argues in the chapter on..., " "the HBR case we looked at last week"]
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
- 🔴 HIGH: Repeated 3+ times, voice emphasis, explicit exam/assessment flagging ("you need to know this, " "this will come up, " "I guarantee there'll be a question on...")
- 🟡 MEDIUM: Explained clearly with examples, given significant lecture time
- 🟢 LOW: Mentioned in passing, tangential, responded to student question without elaboration

List each key point with its code.

FORMAT: Professional UK academic English. Markdown.

CLEANED TRANSCRIPT:
{transcript}"""

BUSINESS_STAGE_3A = """Review this business lecture analysis for quality. Check each item against the original cleaned transcript.

FLAG:
1. Any claim, statistic, company data, market figure, or citation that does not appear in the transcript → mark as [NOT IN TRANSCRIPT — remove or verify]
2. Any framework application, stakeholder mapping, or industry analysis that was constructed by the analyst rather than stated by the lecturer → mark as [ANALYST ADDITION — verify appropriateness]
3. Any quote marked as "verbatim" that has been altered during cleaning → downgrade to "approximate"
4. Any practice question that tests content not covered in this lecture → mark as [OUT OF SCOPE]
5. Any reading reference marked "High confidence" without strong evidence (e.g., specific author + title mentioned) → downgrade to Medium or Low
6. Any company data that has been rounded, adjusted, or standardised from what was actually stated → restore original phrasing
7. Any framework critique or limitation attributed to the lecturer that was actually added by the analyst → mark as [ANALYST ADDITION]

Output the analysis with corrections applied and a brief summary of changes made.

ANALYSIS TO VERIFY:
{transcript}

ORIGINAL CLEANED TRANSCRIPT FOR REFERENCE:
{cleaned_transcript}"""

BUSINESS_STAGE_3B = """Create a one-page A4 revision cheat sheet from this business lecture analysis. Aim for maximum information density — this is a revision aid, not a summary.

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

VERIFIED ANALYSIS:
{transcript}"""

# Define the Business Lecture processing pipeline
BUSINESS_LECTURE_STAGES = [
    ProcessingStage(
        name="clean",
        prompt_template=BUSINESS_STAGE_1,
        system_message="You are a professional academic transcription editor specialising in UK university business and management lectures. Clean transcripts with UK spelling and preserve business terminology exactly as stated.",
        filename_suffix="_clean",
        save_intermediate=True
    ),
    ProcessingStage(
        name="analyze",
        prompt_template=BUSINESS_STAGE_2A,
        system_message="You are a UK business school academic assistant. Transform lecture transcripts into structured study guides with models, frameworks, case studies, and strategic analysis.",
        filename_suffix="_analysis",
        save_intermediate=True
    ),
    ProcessingStage(
        name="qa_verify",
        prompt_template=BUSINESS_STAGE_3A,
        system_message="You are a quality assurance reviewer for academic content. Verify that all claims in the analysis are supported by the original transcript.",
        filename_suffix="_qa_verified",
        save_intermediate=True
    ),
    ProcessingStage(
        name="cheat_sheet",
        prompt_template=BUSINESS_STAGE_3B,
        system_message="You are an academic study guide creator. Create dense, information-packed revision materials from verified lecture analysis.",
        filename_suffix="_cheatsheet",
        save_intermediate=True
    ),
]

# Define the Social Work Lecture processing pipeline
SOCIAL_WORK_LECTURE_STAGES = [
    ProcessingStage(
        name="pre_filter",
        prompt_template=SOCIAL_WORK_PRE_STAGE_1,
        system_message="You are a professional academic transcription editor specialising in UK university lectures. Filter out immaterial student chatter while preserving all teaching content.",
        filename_suffix="_filtered",
        save_intermediate=True
    ),
    ProcessingStage(
        name="clean",
        prompt_template=SOCIAL_WORK_STAGE_1,
        system_message="You are a professional academic transcription editor specialising in UK university lectures. Clean transcripts with UK spelling and proper academic formatting.",
        filename_suffix="_clean",
        save_intermediate=True
    ),
    ProcessingStage(
        name="analyze",
        prompt_template=SOCIAL_WORK_STAGE_2,
        system_message="You are a UK social work academic assistant. Transform lecture transcripts into structured study guides with statutory frameworks and practice scenarios.",
        filename_suffix="_analysis",
        save_intermediate=True
    ),
    ProcessingStage(
        name="qa_verify",
        prompt_template=SOCIAL_WORK_STAGE_3A,
        system_message="You are a quality assurance reviewer for academic content. Verify that all claims in the analysis are supported by the original transcript.",
        filename_suffix="_qa_verified",
        save_intermediate=True
    ),
    ProcessingStage(
        name="cheat_sheet",
        prompt_template=SOCIAL_WORK_STAGE_3B,
        system_message="You are an academic study guide creator. Create dense, information-packed revision materials from verified lecture analysis.",
        filename_suffix="_cheatsheet",
        save_intermediate=True
    ),
]


# Profile configurations for different users/degree programs
# Each profile defines how to process files from a specific upload folder
DEGREE_PROFILES = {
    "social_work_lecture": {
        "name": "Social Work Lecture",
        "description": "Multi-stage processing for social work lectures with statutory analysis",
        "pipeline_type": "multi_stage",
        "skip_diarization": True,
        "stages": SOCIAL_WORK_LECTURE_STAGES,
        "output_formats": ["md"],  # Only markdown for intermediate files
        "file_prefix_pattern": "{date}_{topic}",  # Will be customized
    },
    "business_lecture": {
        "name": "Business Management Lecture", 
        "description": "Multi-stage processing for business lectures with strategic analysis, case studies, and frameworks",
        "pipeline_type": "multi_stage",
        "skip_diarization": True,
        "stages": BUSINESS_LECTURE_STAGES,
        "output_formats": ["md"],
        "file_prefix_pattern": "{date}_{topic}",
    },
}

# Map upload folders to degree profiles
FOLDER_PROFILE_MAP = {
    "kate": "social_work_lecture",
    "keira": "business_lecture",  # Ready for next week
}


class DeepSeekFormatter:
    """
    A formatter class that uses the DeepSeek API to format transcripts.
    
    Uses OpenAI-compatible API to format raw transcripts into structured
    markdown notes based on the note type.
    
    Attributes:
        api_key: The DeepSeek API key.
        model: The model to use for formatting (default: deepseek-chat).
        base_url: The base URL for the DeepSeek API.
        client: The OpenAI client instance.
    """
    
    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com/v1"
    ):
        """
        Initialize the DeepSeekFormatter.
        
        Args:
            api_key: The DeepSeek API key.
            model: The model to use for formatting. Defaults to "deepseek-chat".
            base_url: The base URL for the DeepSeek API.
               Defaults to "https://api.deepseek.com/v1".
        """
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        
        # Import openai here to avoid dependency issues if not installed
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError(
                "The 'openai' package is required to use DeepSeekFormatter. "
                "Install it with: pip install openai"
            ) from e
        
        # Initialize the OpenAI-compatible client
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
    
    def _get_prompt(self, note_type: str, transcript: str) -> str:
        """
        Get the appropriate prompt for the note type.
        
        Args:
            note_type: The type of note (MEETING, SUPERVISION, CLIENT, LECTURE, BRAINDUMP).
            transcript: The raw transcript to format.
        
        Returns:
            The formatted prompt string.
        
        Raises:
            FormattingError: If the note type is not supported.
        """
        note_type_upper = note_type.upper()
        
        if note_type_upper not in PROMPT_TEMPLATES:
            supported_types = ", ".join(PROMPT_TEMPLATES.keys())
            raise FormattingError(
                f"Unsupported note type: {note_type}. "
                f"Supported types are: {supported_types}"
            )
        
        return PROMPT_TEMPLATES[note_type_upper].format(transcript=transcript)
    
    def _call_api(
        self, 
        prompt: str, 
        system_message: str = None,
        model: str = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        timeout: int = 120,
        max_retries: int = 3
    ) -> str:
        """
        Call the DeepSeek API with retry logic.
        
        Args:
            prompt: The formatted prompt to send to the API.
            system_message: Optional custom system message.
            model: Model to use (defaults to self.model).
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retry attempts.
        
        Returns:
            The formatted response from the API.
        
        Raises:
            FormattingError: If all retry attempts fail.
        """
        last_error = None
        use_model = model or self.model
        
        # Default system message if not provided
        if system_message is None:
            system_message = (
                "You are a helpful assistant that formats transcripts "
                "into well-structured markdown documents. "
                "Be thorough but concise. Use proper markdown formatting."
            )
        
        for attempt in range(1, max_retries + 1):
            try:
                logger.debug(f"API call attempt {attempt}/{max_retries}")
                
                response = self.client.chat.completions.create(
                    model=use_model,
                    messages=[
                        {
                            "role": "system",
                            "content": system_message
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout
                )
                
                # Log the response for debugging
                formatted_response = response.choices[0].message.content
                logger.debug(f"API response received (attempt {attempt})")
                
                return formatted_response
                
            except Exception as e:
                last_error = e
                logger.warning(f"API call failed (attempt {attempt}/{max_retries}): {e}")
                
                if attempt < max_retries:
                    # Exponential backoff: wait 1s, then 2s, then 4s
                    wait_time = 2 ** (attempt - 1)
                    logger.debug(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"All {max_retries} attempts failed")
        
        # All retries exhausted
        raise FormattingError(
            f"Failed to format transcript after {max_retries} attempts. "
            f"Last error: {last_error}"
        )
    
    def format_transcript(
        self,
        transcript: str,
        note_type: str,
        metadata: Optional[dict] = None
    ) -> str:
        """
        Format a transcript into structured markdown.
        
        Args:
            transcript: The raw transcript text to format.
            note_type: The type of note (MEETING, SUPERVISION, CLIENT, LECTURE, BRAINDUMP).
            metadata: Optional metadata dictionary (reserved for future use).
        
        Returns:
            The formatted markdown string. If formatting fails, returns the
            raw transcript with an error notice prepended.
        """
        # Log the prompt and input for debugging
        logger.info(f"Formatting transcript of type: {note_type}")
        logger.debug(f"Transcript length: {len(transcript)} characters")
        
        try:
            # Get the appropriate prompt
            prompt = self._get_prompt(note_type, transcript)
            logger.debug(f"Using prompt template for: {note_type.upper()}")
            
            # Log the full prompt for debugging
            logger.debug(f"Prompt sent to API:\n{prompt}")
            
            # Call the API with retry logic
            formatted_result = self._call_api(prompt)
            
            # Log the response
            logger.debug(f"Formatted response:\n{formatted_result}")
            logger.info("Transcript formatted successfully")
            
            return formatted_result
            
        except FormattingError as e:
            logger.error(f"Formatting error: {e}")
            # Fall back to raw transcript with error notice
            return (
                f"<!-- Formatting failed: {e} -->\n\n"
                f"# Raw Transcript\n\n"
                f"{transcript}"
            )
        except Exception as e:
            logger.error(f"Unexpected error during formatting: {e}")
            # Fall back to raw transcript with error notice
            return (
                f"<!-- Unexpected formatting error: {e} -->\n\n"
                f"# Raw Transcript\n\n"
                f"{transcript}"
            )


class MultiStageFormatter(DeepSeekFormatter):
    """
    Multi-stage formatter for degree-specific lecture processing.
    
    Extends DeepSeekFormatter to run transcripts through multiple sequential
    processing stages (e.g., filter → clean → analyze → QA → cheat sheet).
    
    Each stage's output becomes the next stage's input. All intermediate
    outputs are saved for review.
    
    Attributes:
        api_key: The DeepSeek API key.
        profile_name: Name of the degree profile to use (e.g., "social_work_lecture").
        stages: List of ProcessingStage objects defining the pipeline.
    """
    
    def __init__(
        self,
        api_key: str,
        profile_name: str = "social_work_lecture",
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com/v1"
    ):
        """
        Initialize the MultiStageFormatter.
        
        Args:
            api_key: The DeepSeek API key.
            profile_name: The degree profile to use. Must exist in DEGREE_PROFILES.
            model: The model to use for formatting. Defaults to "deepseek-chat".
            base_url: The base URL for the DeepSeek API.
        """
        super().__init__(api_key, model, base_url)
        
        if profile_name not in DEGREE_PROFILES:
            available = ", ".join(DEGREE_PROFILES.keys())
            raise FormattingError(
                f"Unknown degree profile: {profile_name}. "
                f"Available: {available}"
            )
        
        self.profile_name = profile_name
        self.profile = DEGREE_PROFILES[profile_name]
        self.stages = self.profile.get("stages", [])
        
        logger.info(f"MultiStageFormatter initialized with profile: {profile_name}")
        logger.info(f"Pipeline has {len(self.stages)} stages")
    
    def process_transcript(
        self,
        transcript: str,
        metadata: Optional[dict] = None
    ) -> Dict[str, str]:
        """
        Process a transcript through all stages of the pipeline.
        
        Args:
            transcript: The raw transcript from Whisper.
            metadata: Optional metadata (filename, duration, etc.).
        
        Returns:
            Dictionary mapping stage names to their outputs.
            Includes 'final' key with the last stage's output.
        """
        results = {
            "raw_input": transcript,
            "profile": self.profile_name,
        }
        
        current_input = transcript
        previous_outputs = {}
        
        logger.info(f"Starting {len(self.stages)}-stage processing pipeline")
        
        for i, stage in enumerate(self.stages, 1):
            logger.info(f"Stage {i}/{len(self.stages)}: {stage.name}")
            
            try:
                # Prepare the prompt with current input
                # Some stages need access to previous outputs (e.g., Stage 3A needs clean transcript)
                if "{cleaned_transcript}" in stage.prompt_template and "clean" in previous_outputs:
                    prompt = stage.prompt_template.format(
                        transcript=current_input,
                        cleaned_transcript=previous_outputs.get("clean", current_input)
                    )
                else:
                    prompt = stage.prompt_template.format(transcript=current_input)
                
                # Call API with stage-specific settings
                output = self._call_api(
                    prompt=prompt,
                    system_message=stage.system_message,
                    model=stage.model,
                    temperature=stage.temperature,
                    max_tokens=stage.max_tokens,
                    timeout=stage.timeout
                )
                
                # Store result
                results[stage.name] = output
                results[f"{stage.name}_suffix"] = stage.filename_suffix
                
                # Update for next stage
                current_input = output
                previous_outputs[stage.name] = output
                
                logger.info(f"  ✓ Stage {stage.name} complete ({len(output)} chars)")
                
            except Exception as e:
                logger.error(f"  ✗ Stage {stage.name} failed: {e}")
                # Include error in results but don't stop pipeline
                results[stage.name] = f"<!-- ERROR in stage {stage.name}: {e} -->\n\n{current_input}"
                results[f"{stage.name}_error"] = str(e)
                # Continue with current input (pass-through on error)
        
        # Mark final output
        if self.stages:
            results["final"] = current_input
            results["final_suffix"] = self.stages[-1].filename_suffix
        else:
            results["final"] = transcript
            results["final_suffix"] = ""
        
        logger.info("Multi-stage processing complete")
        return results
    
    def get_stage_outputs(self, results: Dict[str, str]) -> List[Dict]:
        """
        Extract list of stage outputs that should be saved as files.
        
        Args:
            results: The dictionary returned by process_transcript().
        
        Returns:
            List of dicts with 'stage', 'suffix', and 'content' keys.
        """
        outputs = []
        
        for stage in self.stages:
            if stage.name in results and stage.save_intermediate:
                outputs.append({
                    "stage": stage.name,
                    "suffix": stage.filename_suffix,
                    "content": results[stage.name]
                })
        
        return outputs


def get_profile_for_folder(folder_name: str) -> Optional[str]:
    """
    Get the degree profile name for a given upload folder.
    
    Args:
        folder_name: Name of the upload folder (e.g., "kate", "keira").
    
    Returns:
        Profile name if mapped, None otherwise.
    """
    return FOLDER_PROFILE_MAP.get(folder_name.lower())


def should_skip_diarization(folder_name: str) -> bool:
    """
    Check if diarization should be skipped for a given folder.
    
    Args:
        folder_name: Name of the upload folder.
    
    Returns:
        True if diarization should be skipped, False otherwise.
    """
    profile_name = get_profile_for_folder(folder_name)
    if profile_name and profile_name in DEGREE_PROFILES:
        return DEGREE_PROFILES[profile_name].get("skip_diarization", False)
    return False
