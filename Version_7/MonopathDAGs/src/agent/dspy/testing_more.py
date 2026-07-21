from typing import List, Dict
import dspy
import dspy.predict
from dspy import Signature
import os

# 1. Load text from PDF
from src.data.data_processors.pdf_to_text import extract_text_from_pdf

# 2. Use paragraph extractor
def extract_paragraphs(text: str) -> List[dict]:
    import re
    section_headers = [
        "Abstract", "Introduction", "Case Presentation", "Case Description",
        "Investigation", "Diagnosis", "Treatment", "Follow-up", "Outcome",
        "Discussion", "Conclusion", "Background", "Clinical Findings",
        "Therapeutic Intervention"
    ]
    section_pattern = re.compile(rf"^\s*({'|'.join(section_headers)}):?\s*$", re.IGNORECASE)
    current_section = "Unknown"
    blocks = []
    raw_paragraphs = re.split(r"\n\s*\n", text)

    for para in raw_paragraphs:
        para = para.strip()
        if not para:
            continue
        header_match = section_pattern.match(para)
        if header_match:
            current_section = header_match.group(1).title()
            continue
        if len(para.split()) < 5:
            continue
        blocks.append({
            "section": current_section,
            "paragraph": para
        })
    return blocks

# paragraphs = extract_paragraphs(raw_text)
# gemini_api_key=os.environ.get("GEMINI_API_KEY","")
# # 3. Configure DSPy LLM and module
# lm = dspy.LM('ollama_chat/llama3.1', api_base='http://localhost:11434',cache=True, api_key='')

# dspy.configure(lm=lm, adapter=dspy.ChatAdapter())

class clinicalEventExtract(dspy.Signature):
    """
    You are a medical extraction assistant.

    Your task is to read one paragraph from a clinical case report and extract a list of distinct, ordered, and atomic clinical events that relate directly to the patient.

    You must include:
    - Events that are explicitly stated or reasonably inferred.
    - Clinical facts, diagnostic actions, interventions, interpretations, adverse effects, and administrative decisions — all must be patient-specific.
    - Ephemeral changes (e.g., lab value changes, symptoms) and non-ephemeral state transitions (e.g., diagnosis, progression, remission).
    - Any referenced prior medical events (e.g., past surgeries) — these should appear early in the timeline.
    - All measurements, units, time references, and agents (if stated).
    - Ambiguous, indeterminate, or speculative findings are valid and should be included if they influence the patient timeline.

    For each extracted event, return a dictionary with:
    - step_index (int): Order in which the event occurred within this paragraph
    - description (str): A clear, atomic statement of what happened
    - temporal_reference (optional, str): Any stated or implied time expression (e.g., "day 5", "two weeks later")
    - event_type (optional, str): A tag like "diagnosis", "treatment", "observation", "procedure", "response", "administrative", etc.
    - agents (optional, list of str): All named roles or actors involved (e.g., "oncologist", "radiologist")
    - value (optional): Any quantitative or qualitative measurement (e.g., "CEA 108 ng/mL", "tumor 1.2 cm")
    - confidence (float): Confidence in the accuracy of this extraction (0–1)
    - source_sentence (str): Exact sentence or phrase this event came from

    Each event should be atomic — if one sentence includes multiple actions or outcomes, split them into multiple entries.

    Do not include general background facts, only information about this specific patient.

    Do not normalize or rephrase time references — include them as stated.
    """

    report_text: str = dspy.InputField(desc="A paragraph of clinical narrative from a case report")
    events: List[Dict] = dspy.OutputField(desc="List of distinct, ordered, atomic clinical events")



# what do you feel would work step wise, =->
extractor = dspy.Predict(clinicalEventExtract)

# result2=extractor(raw_text)
# 4. Run LLM on each paragraph
# for i, p in enumerate(paragraphs):
#     # print(f"\n[{p['section']}] Paragraph {i+1}:\n{p['paragraph']}\n")
#     result = extractor(report_text=p['paragraph'])
#     print(result)
#     for event in result.events:
#         print(event)
        # print(f"- ({event['step_index']}) {event['description']}")
# the following should be done in this cs

# decompose_signature-> outputs should be decomposable-> 
# once it is decomposable might be easier, sentence by sentence
# byte pair encoding versoin of composable facts, 
#

class decomposeToAtomicSentences(dspy.Signature):
    """
    Given a single complex sentence from a clinical case report,
    return a list of atomic clinical sentences.

    Each atomic sentence must:
    - Contain only one clinical event, action, or state
    - Be clear, self-contained, and refer only to the patient
    - Preserve all quantitative values, agents, and time references
    - Be directly traceable to the original sentence (no hallucination)
    - Be suitable for downstream structuring into graph nodes or facts

    Do NOT summarize, group, or abstract across multiple concepts.

    If the sentence is already atomic, return it as a single-item list.

    Output: list of atomic clinical sentences (strings)
    """

    sentence: str = dspy.InputField(desc="A complex clinical sentence from a case report")
    context: str = dspy.InputField(optional=True, desc="Optional failure reason or context to improve decomposition")
    atomic_sentences: List[str] = dspy.OutputField(desc="List of decomposed atomic sentences")
# atomic_sent=dspy.Predict(decomposeToAtomicSentences)
decomposeToAtomicSentences.__doc__ = """
    Given a single complex sentence from a clinical case report,
    return a list of atomic clinical sentences.

    Each atomic sentence must:
    - Contain only one clinical event, action, or state
    - Be clear, self-contained, and refer only to the patient
    - Preserve all quantitative values, agents, and time references
    - Be directly traceable to the original sentence (no hallucination)
    - Be suitable for downstream structuring into graph nodes or facts
    Do NOT summarize, group, or abstract across multiple concepts.

    If the sentence is already atomic, return it as a single-item list.

If this sentence was previously marked as non-atomic because: {context}, be especially careful to avoid that issue.
"""


class checkIfAtomic(dspy.Signature):
    """
    Determine whether a clinical sentence is atomic.

    A sentence is atomic if:
    - It describes exactly one clinical event, action, or state affecting the patient
    - It does not combine multiple separate actions or changes
    - It is self-contained and unambiguous
    - It includes relevant detail (e.g., time, agent, value) if present in the original source

    Return:
    - is_atomic (bool): True if sentence is atomic
    - reason (str): Why it passed or failed
    """

    sentence: str = dspy.InputField()
    is_atomic: bool = dspy.OutputField()
    reason: str = dspy.OutputField()
checkIfAtomic.__doc__ = """
You are a clinical validator whose job is to strictly determine whether a sentence is atomic.

A sentence is **atomic** ONLY IF ALL of the following are true:
1. It describes exactly ONE clinical action, state, event, or observation.
2. It does NOT include multiple verbs or actions ("and", "then", "also", "while", "which", etc.).
3. It is NOT a compound sentence.
4. It is self-contained and clearly refers to a single patient-specific event.
5. It includes detail about the agent, value, or time if such detail is present in the source.

❗If there are multiple actions, effects, causes, or interpretations — it is NOT atomic.

Be harsh. If you're uncertain, the answer is FALSE.

Return:
- is_atomic (bool): True ONLY if the sentence is minimal and describes exactly one clinical change.
- reason (str): Explain why it is or isn’t atomic.

Examples:
- "The patient underwent a PET scan." → ✅ atomic
- "The scan showed lesions and chemotherapy was started." → ❌ not atomic (two actions)
- "He developed fever while on pembrolizumab." → ❌ not atomic (symptom + treatment context)
"""

decomposeToAtomicSentences_module = dspy.Predict(decomposeToAtomicSentences)
checkIfAtomic_module = dspy.Predict(checkIfAtomic)

def recursively_decompose_to_atomic_sentences(sentence: str, depth: int = 0, max_depth: int = 2, reason: str = "") -> List[str]:
    if depth > max_depth:
        return [sentence]

    # Step 1: Decompose current sentence (add reason to prompt if needed)
    if reason:
        prompt_override = f"The sentence was rejected as atomic because: {reason}"
        atomic_candidates = decomposeToAtomicSentences_module(sentence=sentence, context=prompt_override).atomic_sentences
    else:
        atomic_candidates = decomposeToAtomicSentences_module(sentence=sentence).atomic_sentences

    output = []
    for atomic_candidate in atomic_candidates:
        check = checkIfAtomic_module(sentence=atomic_candidate)

        if check.is_atomic:
            output.append(atomic_candidate)
        else:
            print(f"↪ Re-decomposing: {atomic_candidate} – {check.reason}")
            decomposed = recursively_decompose_to_atomic_sentences(
                sentence=atomic_candidate,
                depth=depth + 1,
                max_depth=max_depth,
                reason=check.reason
            )
            output.extend(decomposed)

    return output



# import pymupdf
# import pymupdf4llm

# raw_text=extract_text_from_pdf("/Users/aaronfanous/Desktop/AnsonProjects/DynamicData/samples/pdfs/case_reports_onc_2025.pdf")
# doc = pymupdf.open("/Users/aaronfanous/Desktop/AnsonProjects/DynamicData/samples/pdfs/case_reports_onc_2025.pdf")

# md= pymupdf4llm.to_markdown("/Users/aaronfanous/Desktop/AnsonProjects/DynamicData/samples/pdfs/case_reports_onc_2025.pdf")

# print(md)
# print(doc.get_toc())
# print(lm("tell me which sections of the TOC beginning and end will have article info" +" TOC:" +str(doc.get_toc())+" \n      only give me answer as \{ 'begin':..., 'end':...  \}  "))
# input_sentence = """ At 17 years post-initial diagnosis, he developed 
# an oligometastatic liver lesion and a lung lesion and underwent partial hepatectomy"""

# # this is not working, 
# atomic_results = recursively_decompose_to_atomic_sentences(input_sentence)

# for i, s in enumerate(atomic_results, 1):
#     print(f"{i}. {s}")
# context length is around 130k, pa

## split



class RecordPatientHistory(dspy.Signature):
    
    """
    You are to keep all the detail and render the patient timeline from the article text, return the information in sequential strs, utilize exact sentences from the article  """
    article_text: str = dspy.InputField(desc="the corpus that you parse")
    patient_history:List[str] = dspy.OutputField(desc=" the entire timeline from start to finish of the patient")


from bs4 import BeautifulSoup

def preprocess_pmc_article_text(html_path: str) -> str:
    """
    Extract clean PMC article text from HTML file,
    excluding any content inside Abstract sections,
    and stopping at References or Bibliography headings.
    Preserves section titles, paragraphs, and tables.

    Args:
        html_path (str): Path to the PMC article HTML file.

    Returns:
        str: Preprocessed article text.
    """
    def is_stop_section(text: str) -> bool:
        """Return True if text signals the start of References or Bibliography."""
        lowered = text.lower()
        return any(keyword in lowered for keyword in ("references", "bibliography"))

    with open(html_path, "r", encoding="utf-8") as file:
        soup = BeautifulSoup(file, "lxml")

    # Remove unwanted tags
    for tag in soup(["script", "style", "header", "footer", "nav", "aside"]):
        tag.decompose()

    # Remove all Abstract sections
    for abstract_tag in soup.find_all(["div", "section"], class_=lambda c: c and "abstract" in c.lower()):
        abstract_tag.decompose()

    # Identify main body
    body = soup.find("body") or soup.find("article") or soup.find("div", class_="body")
    if body is None:
        body = soup

    lines = []

    for tag in body.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "table"]):
        text = tag.get_text(strip=True)
        if not text:
            continue

        if is_stop_section(text):
            break

        if tag.name == "table":
            table_text = []
            for row in tag.find_all("tr"):
                row_text = [cell.get_text(strip=True) for cell in row.find_all(["th", "td"])]
                if row_text:
                    table_text.append("\t".join(row_text))
            if table_text:
                lines.append("\n".join(table_text))
        else:
            lines.append(text)

    return "\n\n".join(lines)


# blockText = dspy.Predict(RecordPatientHistory)
# print(blockText(article_text=raw_text))
# print(lm("with this article text " + raw_text +"\n extract the entire patient history from the case report, be explicit and keep detail"))

# print(dspy.inspect_history())


# chunk overlap within the text, create readable context , update context then continue to improve on it


# steps for iteration on this, start by generating the splites
import spacy
from spacy.cli import download

try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    print("Downloading spaCy model: en_core_web_sm...")
    download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

def split_into_sentences(text, n=3):
    """Split text into sentences and join every n sentences into one string."""
    doc = nlp(text)
    sentences = [sent.text.strip() for sent in doc.sents if sent.text.strip()]
    return [' '.join(sentences[i:i+n]) for i in range(0, len(sentences), n)]
# assume it is split paragraphs,
# after split you process each block

# each block contains stateful inforamation break it down into meaningful sentences. maintain the sentence along with the information. 

# contine




class ExtractPatientStatesFromParagraph(Signature):
    """Extract highly specific, discrete patient states from a paragraph of a case report.
    
    The goal is to identify and extract each distinct patient state or event mentioned, maintaining maximum clinical specificity and avoiding summarization or paraphrasing.
    
    Instructions:
    - Work directly from the paragraph; do not infer or summarize.
    - Extract each specific patient state separately.
    - Preserve factual clinical details exactly as described (e.g., medications administered, vitals recorded, symptoms observed, diagnostics performed).
    - Avoid combining multiple states into one extraction.
    - If no patient state is identifiable in part of the paragraph, omit that part without creating assumptions.
    """
    
    paragraph: str = dspy.InputField(desc="A paragraph from a case report containing clinical descriptions.")
    extracted_states: list[str] = dspy.OutputField(desc="A list of discrete, highly specific patient states extracted directly from the paragraph, maintaining all clinical detail and granularity.")



def analyze_sentences(sentences: list[str]) -> None:
    """Analyze a list of sentences and extract patient states."""
    extractor = dspy.Predict(ExtractPatientStatesFromParagraph)

    for idx, sentence in enumerate(sentences):
        result = extractor(paragraph=sentence)
        print(f"Sentence {idx+1}:")
        print(f"Original: {sentence}")
        print(f"Extracted States: {result.extracted_states}")
        print("-" * 80)
# analyze_sentences(split_into_sentences(raw_text,10))





class ExtractHPIFragments(dspy.Signature):
    """Extract historical patient information (HPI) fragments prior to the onset of the current clinical case.

    Definition of HPI for this task:
    - Chronic conditions (e.g., hypertension, diabetes)
    - Prior medical history (e.g., surgeries, hospitalizations, treatments)
    - Baseline functional status (e.g., ambulatory status, mental baseline)
    - Longstanding lifestyle factors (e.g., smoking, alcohol use, occupational exposures)
    - Demographic background (e.g., age, sex, ethnicity) if relevant to medical history

    DO NOT extract:
    - Presenting symptoms (e.g., 'The patient complained of chest pain')
    - Findings upon admission (e.g., vitals, imaging findings at admission)
    - Any acute changes, complaints, labs, or interventions that occur after presentation
    - Any new diagnostics or treatments after arrival

    Explicit stopping instructions:
    - If the paragraph includes descriptions that suggest the case has started (e.g., 'The patient presented with...', 'On admission...', 'Upon evaluation...'), do not extract anything further, even if historical details are mixed in.

    Output:
    - Return a list of discrete, factual fragments related only to pre-existing historical details.
    - If the paragraph is entirely post-presentation, return an empty list.
    """

    paragraph: str = dspy.InputField(desc="A paragraph from a case report.")
    extracted_fragments: list[str] = dspy.OutputField(
        desc="List of extracted patient history/background fragments before case onset."
    )

class ClassifyHPIFragment(dspy.Signature):
    """Classify an extracted fragment as either past medical history, current presentation, or uncertain.

    Instructions:
    - Label 'past history' if the fragment describes an event, diagnosis, procedure, lifestyle factor, or condition that existed prior to the current hospitalization.
    - Label 'current presentation' if the fragment describes symptoms, findings, diagnostics, or treatments at or after admission.
    - Label 'uncertain' if classification cannot be confidently determined from the fragment alone.

    Also provide a short explanation (1-2 sentences) justifying the classification.
    """

    fragment: str = dspy.InputField(desc="One extracted fragment from case report.")
    classification: str = dspy.OutputField(
        desc="Label as 'past history', 'current presentation', or 'uncertain'."
    )
    explanation: str = dspy.OutputField(
        desc="Short explanation justifying why this fragment was classified this way."
    )

class ConsolidateHPINode(dspy.Signature):
    """Consolidate clean validated history fragments into only history, no patient timeline"""
    history_fragments: list[str] = dspy.InputField(
        desc="List of verified patient history fragments."
    )
    consolidated_hpi: str = dspy.OutputField(
        desc="Final coherent paragraph summarizing pre-existing patient history."
    )

class DetectCaseStart(dspy.Signature):
    """Determine if a paragraph marks the start of the current clinical case.

    Instructions:
    - Return 'True' if the paragraph describes new presenting symptoms, findings on admission, or events during the current hospitalization.
    - Return 'False' if the paragraph still discusses prior history or background only.
    - return false if information is from an abstract
    """

    paragraph: str = dspy.InputField(desc="Paragraph from the case report.")
    case_started: bool = dspy.OutputField(
        desc="True if current case events have started; False if still background history or information is in abstract"
    )
    
class VerifyHPIFragment(dspy.Signature):
    """Verify if a fragment describes true pre-existing patient history (not presentation).

    Must be:
    - Past diagnoses
    - Past procedures
    - Past lifestyle
    - Pre-existing conditions

    """

    fragment: str = dspy.InputField(desc="One fragment from extracted data.")
    is_valid_history: bool = dspy.OutputField(
        desc="True if this fragment describes valid past history. False otherwise."
    )


from tqdm import tqdm

class BuildHPINodeModule(dspy.Module):
    """Extract, classify, and consolidate clean HPI nodes from case report paragraphs with full progress tracking."""

    def __init__(self):
        super().__init__()
        self.extractor = dspy.ChainOfThought(ExtractHPIFragments)
        self.classifier = dspy.ChainOfThought(ClassifyHPIFragment)
        self.consolidator = dspy.ChainOfThought(ConsolidateHPINode)

    def forward(self, paragraphs: list[str]) -> str:
        """Full pipeline: extract, classify, and consolidate fragments into HPI."""
        valid_fragments = []

        all_fragments = []

        # Progress bar over paragraphs
        for paragraph in tqdm(paragraphs, desc="Extracting fragments", ncols=100):
            extraction = self.extractor(paragraph=paragraph)
            all_fragments.extend(extraction.extracted_fragments)

        # Progress bar over individual fragment verification
        for fragment in tqdm(all_fragments, desc="Classifying fragments", ncols=100):
            classification = self.classifier(fragment=fragment)
            if classification.classification == "past history":
                print(classification)
                valid_fragments.append(fragment)

            

        consolidation = self.consolidator(history_fragments=valid_fragments)
        return consolidation.consolidated_hpi



# so you have to be able to pull in the information, 



class CreatePatientTimeline(dspy.Signature):
    "You are a researcher extracting information relative to a timeline. Your goal is find the initial presentation information, from the patient history with respect to the whole article. Any actions indicated to be taken by the team including treatment and actions is considered false, as you go forward you should  "
    previous_timeline: str = dspy.InputField(desc="previously processed information summary")
    paragraph:str= dspy.InputField(desc="independent paragraph or sentences from the case report")
    patient_time_line : str= dspy.OutputField(desc="all information of the patient timeline")
    inital_patient_history:str =dspy.OutputField(desc="only intial patient history, no mangement or treatemnt.")


# path_raw="./samples/html/Small Cell Lung Cancer in the Course of Idiopathic Pulmonary Fibrosis—Case Report and Literature Review - PMC.html"
# raw_text=preprocess_pmc_article_text(path_raw)
# paragraphs=split_into_sentences(raw_text,10)
# patient_timeline=dspy.Predict(CreatePatientTimeline)
# initalstate="Start:"
# patient_initial_states=[]
# for x in paragraphs:
#     timeline_output=patient_timeline(previous_timeline=initalstate,paragraph=x)
#     initalstate+= timeline_output.patient_time_line
#     patient_initial_states.append(timeline_output.inital_patient_history)
#     print(timeline_output)


from typing import Any, Dict, Union
import json
from typing import Any

def pretty_print_json(obj: Any) -> None:
    """Pretty-print a Python object as formatted JSON."""
    print(json.dumps(obj, indent=2, ensure_ascii=False))

import dspy
from typing import Any, Dict



class GenerateNodeFromText(dspy.Signature):
    """
    Generate a single node representing extracted patient state information from a text excerpt.

    The generated node must contain:
    - 'node_id': str, a unique identifier for the node.
    - 'step_index': int, the sequential order of the node.
    - 'summary': str, a concise one-line summary of the patient state.
    - 'data': dict, structured into clear clinical categories.

    For the 'data' field:
    - Organize information into the following top-level categories:
        - Demographics
        - Medical History
        - Social History
        - Lifestyle Factors
        - Symptoms
        - Functional Status
        - Mental Status
        - Review of Systems (ROS)
        - Diagnoses
        - Medications
        - Allergies
        - Vitals
        - Labs
        - Imaging
        - Procedures
    - Each entry inside a category must be a dictionary with:
        - 'value': the actual extracted data (e.g., measurement, condition, observation, boolean, etc.)
        - 'evidence': the exact text fragment supporting this data extraction.

    Additional requirements:
    - Prefer structured, specific values (e.g., dose + frequency for medications, value + unit for labs/vitals).
    - Do not hallucinate; only populate fields with clear evidence from the provided text.
    - Maintain consistent formatting for all entries to allow structured parsing.
    - Include observation timestamp or offset day if available.

    Example:
    {
      "Blood Pressure": {
        "value": {"systolic": 130, "diastolic": 85, "unit": "mmHg"},
        "evidence": "Blood pressure measured at 130/85 mmHg."
      }
    }
    """

    text: str = dspy.InputField(desc="The text excerpt describing the patient's state, clinical findings, and relevant information.")

    node: Dict[str, Any] = dspy.OutputField(
        desc="A dictionary representing a single structured node including extracted patient state information and source evidence."
    )



# patient_initial_states[-1]
# generateNode=dspy.Predict(GenerateNodeFromText)


# pretty_print_json(generateNode(text=patient_initial_states[-1]).node)













# import dspy
# from typing import List, Dict

# # Signature 1: Classify the paragraph impact
# class ClassifyParagraphImpact(dspy.Signature):
#     """
#     Classify whether the paragraph contains:
#     - PatientEvent (direct patient update)
#     - BackgroundInfo (general medical background)
#     - Noise (irrelevant content)
#     """
#     paragraph: str = dspy.InputField(desc="Paragraph to classify.")

#     impact_type: str = dspy.OutputField(desc="PatientEvent, BackgroundInfo, or Noise.")
#     classification_reasoning: str = dspy.OutputField(desc="Reason for classification decision.")

# # Signature 2: Extract atomic patient events with direct evidence
# class ExtractPatientEvents(dspy.Signature):
#     """
#     Extract atomic patient-specific events with evidence.

#     Requirements:
#     - Only extract events directly describing THIS patient's real state, treatment, diagnosis, symptoms, or outcomes.
#     - Every extracted event MUST have:
#       - 'event_summary': concise description of the patient event.
#       - 'evidence_fragment': exact sentence or fragment from the paragraph that supports it.
#     - If multiple events are in one paragraph, extract each separately.
#     - Ignore general medical background, research studies, mechanisms, and unrelated theory.
#     - DO NOT guess or invent if no direct evidence exists.
#     - DO NOT extract if there is no patient-specific evidence.

#     Example Valid Event:
#     {
#       "event_summary": "Patient presented with cough and dyspnea in September 2014.",
#       "evidence_fragment": "A 38-year-old Chinese man with no smoking history presented with cough and dyspnoea in September 2014."
#     }
#     """
#     paragraph: str = dspy.InputField(desc="Paragraph of clinical text.")

#     extracted_events: List[Dict[str, str]] = dspy.OutputField(
#         desc="List of atomic patient-specific events with mandatory evidence."
#     )



# # Predictors
# classify_impact = dspy.Predict(ClassifyParagraphImpact)
# extract_events = dspy.Predict(ExtractPatientEvents)

# # Timeline memory
# timeline_text = "Patient timeline starts:"
# evidence_fragments = []
# full_history = []

# # Paragraph processing loop
# for idx, paragraph in enumerate(paragraphs):
#     impact = classify_impact(paragraph=paragraph)

#     history_entry = {
#         "paragraph_index": idx,
#         "paragraph_text": paragraph,
#         "impact_type": impact.impact_type,
#         "classification_reasoning": impact.classification_reasoning,
#     }

#     if impact.impact_type == "PatientEvent":
#         events_output = extract_events(paragraph=paragraph)

#         valid_events = []
#         if events_output.extracted_events:
#             for e in events_output.extracted_events:
#                 if (
#                     isinstance(e, dict)
#                     and "evidence_fragment" in e
#                     and e["evidence_fragment"].strip() != ""
#                     and any(keyword in e["evidence_fragment"].lower() for keyword in ["patient", "he", "she", "man", "woman", "underwent", "was treated", "was diagnosed", "presented"])
#                 ):
#                     valid_events.append(e)


#         for event in valid_events:
#             timeline_text += " " + event["event_summary"]
#             evidence_fragments.append(event["evidence_fragment"])

#         history_entry["extracted_events"] = valid_events
#     else:
#         history_entry["extracted_events"] = []

#     history_entry["updated_timeline_text"] = timeline_text
#     full_history.append(history_entry)

import dspy
from typing import List, Dict, Any

class PatientTimeline(dspy.Signature):
    """
    Your task is to extract structured patient timeline from a clinical paragraph. First evaluate if the information is part of the clinical case, or just introduction.
    Your goal is to verify that it is a part of the clinical case and keep patient management and care in order. 
    your goal is to include everything including lab findings
    INCLUDE ALL LAB FINDINGS VERBATIM AND ALL IMAGING FINDINGS VERBATIM
    ONLY INCLUDE PATIENT DATA
    DO NOT BULLET POINT, this is a str output, keep specific lab and imaging in as well as procedure values. No explanations
    """

    paragraph: str = dspy.InputField(desc="Paragraph of clinical text to extract patient information from.")
    previous_memory: List[str] = dspy.InputField(desc="List of patient history extracted so far.")

    # nodes: List[Dict[str, Any]] = dspy.OutputField(
    #     desc="List of new structured patient state nodes extracted from the paragraph."
    # )
    pt_timeline: str = dspy.OutputField(
        desc="Concatenated highly specific human-readable patient timeline including new events extracted in order."

    )
    #steps in this case are evaluate the ordering, and the

# class CreateEdge(dspy.Signature):
#     """
    


#     Args:
#         dspy (_type_): _description_
#     """
# class CheckEdges(dspy.Signature):
#     """
#     Check if the edges are possible to get the followigk




#     """
    
#     first_edge:dspy.InputField(desc="")




class BuildNodes(dspy.Signature):
    """ build fully json compliant nodes of each sentence you are given splitting per atomic entity with reference to the patient, each node must have a step index increasing iteratively
    step
    step_index:int
    clinical_data = {}
        "medications": [
            {

            }
        ],
        "vitals": [
            {
              
            }
        ],
        "labs": [
            {
        }
        ],
        "imaging": [
            {
         
            }
        ],
        "procedures": [
            {
          
            }
        ],
        "HPI": [
            {
            
            }
        ],
        "ROS": [
            {
              
            }
        ],
        "functional_status": [
            {
              
            }
        ],
        "mental_status": [
            {
             
            }
        ],
        "social_history": [
            {
            }
        ],
        "allergies": [
            {
          
            }
        ],
        "diagnoses": [
            {
        
            }
        ]

    """
    previous_step_index:int = dspy.InputField(desc="previous step index ")
    sentence_to_parse:str = dspy.InputField(desc="sentence to parse atomically for all independent enities relative to patient")
    outputNodes:List[Dict[str,Any]]=dspy.OutputField(desc="list of nodes to represent the patient snapshot ")
    

    # If you want to see the raw nodes:
    # pretty_print_json(output.nodes)

# builder = BuildHPINodeModule()
# final_hpi = builder(split_into_sentences(raw_text,10))
# print(final_hpi)
# print(dspy.inspect_history(30))

class ClassifyBranchingEdges(dspy.Signature):
    """

    With a an edge A and an Edge B, your goal is to ascertain whether edge B is the opposite or reverses Edge
    """

    # start_node=dspy.InputField(desc="")
    EdgeA=dspy.InputField(desc="edge to compare to")

    EdgeB=dspy.InputField(desc="edge to classify as opposite or reversing the comparison edge")
    # end_node=dspy.InputField(desc="")
    

    branch_reversible:bool= dspy.OutputField(desc="bool indicating if edge b is opposite or reversing edge a")
    reason=dspy.OutputField(desc="why you made the decision?")


#
from dotenv import load_dotenv
import os

def __main__():



    load_dotenv("./.config/.env")
    gemini_api_key=os.environ.get("GEMINI_APIKEY","")
    gptkey = os.environ.get("GPTKEY","")

    

# 3. Configure DSPy LLM and module
    # lm = dspy.LM('ollama_chat/llama3.1', api_base='http://localhost:11434',cache=True, api_key='')
    # lm = dspy.LM('gemini/gemini-2.0-flash', api_key=gemini_api_key,temperature=0.3)

    # dspy.configure(lm=lm, adapter=dspy.ChatAdapter())


#     edge1 = """
# Edge 1: edge_id = A_to_B
# {
#  'content': 'Patient started systemic corticosteroid therapy (prednisone 40 mg daily) '
#             'to manage suspected interstitial lung disease, following assessment of symptoms '
#             'and initial imaging.',
#  'edge_id': 'A_to_B'}
# """
#     edge2 = """
# Edge 5: edge_id = E_to_F
# {
#  'content': 'Systemic corticosteroid therapy (prednisone) was discontinued due to clinical stability '
#             'and tapering protocol completion, with decision supported by follow-up evaluations.',
#  'edge_id': 'E_to_F',
#  'transition_event': {'change_type': 'management',
#                       'target_domain': 'treatment',
#                       'trigger_entities': ['C0032961'],
#                       'trigger_type': 'medication_stop'}}
# """
    edge1 = """ 
    Edge 1: edge_id = A_to_B
    {'content': 'Patient initiated on methotrexate for management of interstitial lung disease, '
                'following multidisciplinary team recommendation and baseline laboratory clearance.',
    'edge_id': 'A_to_B'}
    """

    edge2 = """
    Edge 5: edge_id = E_to_F
    {'content': 'Due to intolerance and adverse gastrointestinal reactions, patient transitioned to an alternative immunosuppressive regimen using mycophenolate mofetil, with careful dose escalation and monitoring.',
    'edge_id': 'E_to_F',
    'transition_event': {'change_type': 'medication_substitution',
                        'target_domain': 'treatment',
                        'trigger_entities': ['C0025677'],
                        'trigger_type': 'medication_start'}}
    """
    

    # edging=dspy.Predict(ClassifyBranchingEdges)

    # print(edging(EdgeA=edge1,EdgeB=edge2))
    
    if (True):
        return


    # everything after wards needs to be ignored 

    raw_text=preprocess_pmc_article_text("./samples/html/Small Cell Lung Cancer in the Course of Idiopathic Pulmonary Fibrosis—Case Report and Literature Review - PMC.html")
    split_into_sentences(raw_text,10)
    paragraphs=split_into_sentences(raw_text,10)
    predict_patient_timeline = dspy.Predict(PatientTimeline)
    nodebuilding=dspy.Predict(BuildNodes)
    # Initialize memory
    prev_memory = [""]

    for paragraph in paragraphs:
        output = predict_patient_timeline(
            paragraph=paragraph,
            previous_memory=[prev_memory[-1]]
        )
        
        # Only extend memory with nodes
        prev_memory.append(output.pt_timeline)
        
        # Print human-readable timeline (optional)
        print("-"*30,output.pt_timeline)

    y = split_into_sentences(prev_memory[-1],2)
    valueToStart=0
    for x in y:
        # with dspy.context( lm=dspy.LM('ollama_chat/llama3.1', api_base='http://localhost:11434',cache=True, api_key='')):
            print("-"*80,x,"-"*80)
            atomic_results = recursively_decompose_to_atomic_sentences(x)
            print(atomic_results)
            nodes_probably=nodebuilding(previous_step_index=valueToStart,sentence_to_parse=x )
            pretty_print_json(nodes_probably.outputNodes)
            valueToStart= nodes_probably.outputNodes[-1]["step_index"]

            # this issue so far is that it is not able to handle independent step indexe... 
            # need to create independent ones or pass in 


if __name__=="__main__":

    # 
    __main__()