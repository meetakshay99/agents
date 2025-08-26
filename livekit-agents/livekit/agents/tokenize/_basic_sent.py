import re


# rule based segmentation based on https://stackoverflow.com/a/31505798, works surprisingly well
def split_sentences(
    text: str, min_sentence_len: int = 20, retain_format: bool = False
) -> list[tuple[str, int, int]]:
    """
    the text may not contain substrings "<prd>" or "<stop>"
    """
    
    # Step 1: Protect XML tags and their attributes
    xml_placeholders = {}
    xml_counter = 0
    
    # Find all XML-like tags (including self-closing ones)
    xml_pattern = r'<[a-zA-Z][^>]*/?>'
    
    def replace_xml(match):
        nonlocal xml_counter
        placeholder = f"__XML_PLACEHOLDER_{xml_counter}__"
        xml_placeholders[placeholder] = match.group(0)
        xml_counter += 1
        return placeholder
    
    # Replace XML tags with placeholders
    protected_text = re.sub(xml_pattern, replace_xml, text)
    
    # Step 2: Apply existing sentence splitting logic to protected text
    alphabets = r"([A-Za-z])"
    prefixes = r"(Mr|St|Mrs|Ms|Dr)[.]"
    suffixes = r"(Inc|Ltd|Jr|Sr|Co)"
    starters = r"(Mr|Mrs|Ms|Dr|Prof|Capt|Cpt|Lt|He\s|She\s|It\s|They\s|Their\s|Our\s|We\s|But\s|However\s|That\s|This\s|Wherever)"  # noqa: E501
    acronyms = r"([A-Z][.][A-Z][.](?:[A-Z][.])?)"
    websites = r"[.](com|net|org|io|gov|edu|me)"
    digits = r"([0-9])"
    multiple_dots = r"\.{2,}"

    # fmt: off
    if retain_format:
        protected_text = protected_text.replace("\n","<nel><stop>")
    else:
        protected_text = protected_text.replace("\n"," ")

    protected_text = re.sub(prefixes,"\\1<prd>", protected_text)
    protected_text = re.sub(websites,"<prd>\\1", protected_text)
    protected_text = re.sub(digits + "[.]" + digits,"\\1<prd>\\2", protected_text)
    # protected_text = re.sub(multiple_dots, lambda match: "<prd>" * len(match.group(0)) + "<stop>", protected_text)
    # TODO(theomonnom): need improvement for ""..." dots", check capital + next sentence should not be  # noqa: E501
    # small
    protected_text = re.sub(multiple_dots, lambda match: "<prd>" * len(match.group(0)), protected_text)
    if "Ph.D" in protected_text:
        protected_text = protected_text.replace("Ph.D.","Ph<prd>D<prd>")
    protected_text = re.sub(r"\s" + alphabets + "[.] "," \\1<prd> ", protected_text)
    protected_text = re.sub(acronyms+" "+starters,"\\1<stop> \\2", protected_text)
    protected_text = re.sub(alphabets + "[.]" + alphabets + "[.]" + alphabets + "[.]","\\1<prd>\\2<prd>\\3<prd>", protected_text)  # noqa: E501
    protected_text = re.sub(alphabets + "[.]" + alphabets + "[.]","\\1<prd>\\2<prd>", protected_text)
    protected_text = re.sub(r" "+suffixes+"[.] "+starters," \\1<stop> \\2", protected_text)
    protected_text = re.sub(r" "+suffixes+"[.]"," \\1<prd>", protected_text)
    protected_text = re.sub(r" " + alphabets + "[.]"," \\1<prd>", protected_text)

    # mark end of sentence punctuations with <stop>
    protected_text = re.sub(r"([.!?。！？])([\"\"''])", "\\1\\2<stop>", protected_text)
    protected_text = re.sub(r"([.!?。！？])(?![\"\"''])", "\\1<stop>", protected_text)

    protected_text = protected_text.replace("<prd>",".")
    # fmt: on

    if retain_format:
        protected_text = protected_text.replace("<nel>", "\n")
    
    # Step 3: Restore XML placeholders before splitting
    def restore_xml(match):
        placeholder = match.group(0)
        return xml_placeholders.get(placeholder, placeholder)
    
    # Restore XML tags
    restored_text = re.sub(r'__XML_PLACEHOLDER_\d+__', restore_xml, protected_text)
    
    # Split sentences
    splitted_sentences = restored_text.split("<stop>")
    final_text = restored_text.replace("<stop>", "")

    sentences: list[tuple[str, int, int]] = []

    buff = ""
    start_pos = 0
    end_pos = 0
    pre_pad = "" if retain_format else " "
    for match in splitted_sentences:
        if retain_format:
            sentence = match
        else:
            sentence = match.strip()
        if not sentence:
            continue

        buff += pre_pad + sentence
        end_pos += len(match)
        if len(buff) > min_sentence_len:
            sentences.append((buff[len(pre_pad) :], start_pos, end_pos))
            start_pos = end_pos
            buff = ""

    if buff:
        sentences.append((buff[len(pre_pad) :], start_pos, len(final_text) - 1))

    return sentences
