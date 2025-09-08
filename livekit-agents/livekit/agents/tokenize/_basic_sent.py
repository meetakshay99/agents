import re
import logging

# Configure logging to display messages
#logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("_basic_sent")

def split_sentences(
    text: str, min_sentence_len: int = 20, retain_format: bool = False
) -> list[tuple[str, int, int]]:
    """
    Split text into sentences while protecting XML tags and quoted content.
    The text may not contain substrings "<prd>" or "<stop>"
    """
    logger.info(f"In split_sentences - input = {text}")
    
    # Step 1: Find and protect XML tags with a more robust approach
    protected_items = {}
    counter = 0
    
    def create_placeholder(content):
        nonlocal counter
        placeholder = f"__PROTECTED_{counter}__"
        protected_items[placeholder] = content
        counter += 1
        return placeholder
    
    # Find and protect complete XML elements (including content)
    def protect_xml_tags(text):
        result = ""
        i = 0
        
        while i < len(text):
            if text[i] == '<':
                # Check if this is a closing tag
                if i + 1 < len(text) and text[i + 1] == '/':
                    # This is a closing tag, treat as regular text since we protect complete elements
                    result += text[i]
                    i += 1
                    continue
                
                # Found start of opening tag - find the tag name first
                tag_start = i
                i += 1
                
                # Skip to find tag name end
                tag_name_start = i
                while i < len(text) and text[i] not in [' ', '>', '/']:
                    i += 1
                
                if i >= len(text):
                    # Malformed tag, treat as regular text
                    result += text[tag_start]
                    i = tag_start + 1
                    continue
                
                tag_name = text[tag_name_start:i]
                
                # Now scan for the complete opening tag
                in_quotes = False
                quote_char = None
                
                while i < len(text):
                    char = text[i]
                    
                    if char in ['"', "'"] and not in_quotes:
                        in_quotes = True
                        quote_char = char
                    elif char == quote_char and in_quotes:
                        in_quotes = False
                        quote_char = None
                    elif char == '>' and not in_quotes:
                        # Check if this is self-closing
                        if i > 0 and text[i-1] == '/':
                            # Self-closing tag
                            tag_end = i + 1
                            full_tag = text[tag_start:tag_end]
                            placeholder = create_placeholder(full_tag)
                            result += placeholder
                            i += 1
                            break
                        else:
                            # Opening tag - now find the matching closing tag
                            i += 1
                            
                            # Find matching closing tag, handling nested tags
                            tag_depth = 1
                            
                            while i < len(text) and tag_depth > 0:
                                if text[i] == '<':
                                    # Check if it's a closing tag
                                    if i + 1 < len(text) and text[i + 1] == '/':
                                        # Find the tag name in closing tag
                                        closing_tag_start = i + 2
                                        j = closing_tag_start
                                        while j < len(text) and text[j] not in [' ', '>']:
                                            j += 1
                                        
                                        if j < len(text):
                                            closing_tag_name = text[closing_tag_start:j]
                                            if closing_tag_name == tag_name:
                                                tag_depth -= 1
                                                # Skip to end of closing tag
                                                while j < len(text) and text[j] != '>':
                                                    j += 1
                                                if j < len(text):
                                                    i = j + 1
                                                else:
                                                    i = j
                                            else:
                                                i += 1
                                        else:
                                            i += 1
                                    else:
                                        # Check if it's another opening tag of same type
                                        opening_tag_start = i + 1
                                        j = opening_tag_start
                                        while j < len(text) and text[j] not in [' ', '>', '/']:
                                            j += 1
                                        
                                        if j < len(text):
                                            opening_tag_name = text[opening_tag_start:j]
                                            if opening_tag_name == tag_name:
                                                tag_depth += 1
                                        i += 1
                                else:
                                    i += 1
                            
                            if tag_depth == 0:
                                # Found complete XML element
                                full_element = text[tag_start:i]
                                placeholder = create_placeholder(full_element)
                                result += placeholder
                                break
                            else:
                                # Unclosed tag, treat as regular text
                                result += text[tag_start]
                                i = tag_start + 1
                                break
                        break
                    
                    i += 1
                else:
                    # Reached end without finding closing >
                    result += text[tag_start]
                    i = tag_start + 1
            else:
                result += text[i]
                i += 1
        
        return result
    
    protected_text = protect_xml_tags(text)
#    logger.info(f"After XML protection: {protected_text}")
#    logger.info(f"Protected items: {protected_items}")
    
    # Step 2: Apply existing sentence splitting logic to protected text
    alphabets = r"([A-Za-z])"
    prefixes = r"(Mr|St|Mrs|Ms|Dr)[.]"
    suffixes = r"(Inc|Ltd|Jr|Sr|Co)"
    starters = r"(Mr|Mrs|Ms|Dr|Prof|Capt|Cpt|Lt|He|She|It|They|Their|Our|We|But|However|That|This|Wherever)\s"
    acronyms = r"([A-Z][.][A-Z][.](?:[A-Z][.])?)"
    websites = r"[.](com|net|org|io|gov|edu|me)"
    digits = r"([0-9])"
    multiple_dots = r"\.{2,}"

    if retain_format:
        protected_text = protected_text.replace("\n", "<nel><stop>")
    else:
        protected_text = protected_text.replace("\n", " ")

    protected_text = re.sub(prefixes, "\\1<prd>", protected_text)
    protected_text = re.sub(websites, "<prd>\\1", protected_text)
    protected_text = re.sub(digits + "[.]" + digits, "\\1<prd>\\2", protected_text)
    protected_text = re.sub(multiple_dots, lambda match: "<prd>" * len(match.group(0)), protected_text)
    
    if "Ph.D" in protected_text:
        protected_text = protected_text.replace("Ph.D.", "Ph<prd>D<prd>")
    
    protected_text = re.sub(r"\s" + alphabets + "[.] ", " \\1<prd> ", protected_text)
    protected_text = re.sub(acronyms + " " + starters, "\\1<stop> \\2", protected_text)
    protected_text = re.sub(alphabets + "[.]" + alphabets + "[.]" + alphabets + "[.]", "\\1<prd>\\2<prd>\\3<prd>", protected_text)
    protected_text = re.sub(alphabets + "[.]" + alphabets + "[.]", "\\1<prd>\\2<prd>", protected_text)
    protected_text = re.sub(r" " + suffixes + "[.] " + starters, " \\1<stop> \\2", protected_text)
    protected_text = re.sub(r" " + suffixes + "[.]", " \\1<prd>", protected_text)
    protected_text = re.sub(r" " + alphabets + "[.]", " \\1<prd>", protected_text)

    # Mark end of sentence punctuations with <stop>
    protected_text = re.sub(r"([.!?。！？])([\"\"''])", "\\1\\2<stop>", protected_text)
    protected_text = re.sub(r"([.!?。！？])(?![\"\"''])", "\\1<stop>", protected_text)

    # After marking sentence boundaries, check if any protected elements end with punctuation
    # and have text following them - this indicates a sentence boundary
    def add_sentence_breaks_after_xml(text):
        # Restore protected items temporarily to check their endings
        temp_text = text
        for placeholder, original in protected_items.items():
            if placeholder in temp_text:
                # Check if the protected element ends with sentence-ending punctuation
                if original.rstrip().endswith(('.', '!', '?', '。', '！', '？')):
                    # Check what comes after this placeholder
                    placeholder_pos = temp_text.find(placeholder)
                    if placeholder_pos != -1:
                        after_pos = placeholder_pos + len(placeholder)
                        if after_pos < len(temp_text):
                            # Look at what comes after the placeholder
                            remaining = temp_text[after_pos:]
                            # If there's a space followed by text, insert sentence break
                            if re.match(r'\s+\S', remaining):
                                temp_text = temp_text[:after_pos] + '<stop>' + temp_text[after_pos:]
        return temp_text
    
    protected_text = add_sentence_breaks_after_xml(protected_text)

    protected_text = protected_text.replace("<prd>", ".")

    if retain_format:
        protected_text = protected_text.replace("<nel>", "\n")
    
    # Step 3: Restore protected content
    def restore_all_protected(text_to_restore):
        for placeholder, original in protected_items.items():
            text_to_restore = text_to_restore.replace(placeholder, original)
        return text_to_restore
    
    restored_text = restore_all_protected(protected_text)
    
    # Split sentences
    splitted_sentences = restored_text.split("<stop>")
    final_text = restored_text.replace("<stop>", "")

    sentences = []
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
            sentences.append((buff[len(pre_pad):], start_pos, end_pos))
            start_pos = end_pos
            buff = ""

    if buff:
        sentences.append((buff[len(pre_pad):], start_pos, len(final_text) - 1))

    logger.info(f"Sentences split response = {sentences}")
    return sentences


#def test_sentence_splitter():
#    """Comprehensive test suite for edge cases"""
#
#    test_cases = [
#        # Original problematic case
#        ('I say, <phoneme alphabet="ipa" ph="ˈpi.kæn">pecan</phoneme>.',
#         1, "Original problem case"),
#
#        # Multiple sentences with XML
#        ('This is sentence one. <phoneme alphabet="ipa" ph="ˈpi.kæn">Pecan</phoneme> is in sentence two. This is sentence three.',
#         3, "Multiple sentences with XML in middle"),
#
#        # XML at start of sentence
#        ('<phoneme alphabet="ipa" ph="ˈpi.kæn">Pecan</phoneme> is delicious. I love it.',
#         2, "XML at start of sentence"),
#
#        # Complex XML with multiple attributes containing periods
#        ('<speak version="1.0" xml:lang="en-US" data="test.value">Hello <phoneme alphabet="ipa" ph="ˈpi.kæn">pecan</phoneme>.</speak>',
#         1, "Complex XML with multiple attributes"),
#
#        # Mixed quotes in XML attributes
#        ('<tag attr1="value.with.dots" attr2=\'single.quote.value\' attr3="more.dots">Content</tag>.',
#         1, "Mixed quote types in attributes"),
#
#        # Self-closing XML tags
#        ('<img src="image.jpg" alt="Description." /> This is after the image.',
#         1, "Self-closing XML tags"),
#
#        # Nested XML
#        ('<root><child attr="val.ue"><grandchild prop="another.value">Text</grandchild></child></root>.',
#         1, "Nested XML with periods"),
#
#        # XML with URLs
#        ('<a href="https://example.com/test.html" title="Test.com">Link</a>. Next sentence.',
#         2, "XML with URLs in attributes"),
#
#        # Regular sentences without XML (control test)
#        ('This is a normal sentence. This is another one.',
#         2, "Normal sentences without XML"),
#
#        # Period at end of attribute and sentence
#        ('<tag attr="value.">Content</tag>.',
#         1, "Period at end of attribute and sentence"),
#
#        # Multiple XML tags in one sentence
#        ('I use <tag1 attr="val.1">item1</tag1> and <tag2 attr="val.2">item2</tag2> together.',
#         1, "Multiple XML tags in one sentence"),
#
#        # XML with content containing periods
#        ('<note>This content has periods. Multiple ones.</note> This is outside.',
#         1, "XML with periods in content"),
#
#        # XML with content containing periods and a period outside.
#        ('<note>This content has periods. Multiple ones.</note>. This is outside.',
#         2, "XML with periods in content and a period outside"),
#
#        # Malformed XML (unclosed quotes) - should handle gracefully
#        ('<tag attr="unclosed quote>Content</tag>.',
#         1, "Malformed XML with unclosed quotes"),
#
#        # Edge case: Empty and complex attributes
#        ('<tag empty="" complex="val.1.2.3" simple="test">Content</tag>.',
#         1, "Empty and complex attributes"),
#
#        # Scientific notation and decimals (should NOT be protected)
#        ('The value is 3.14159. The measurement was 2.5e-10.',
#         2, "Scientific notation - should split normally"),
#
#        # Abbreviations that should be protected
#        ('Dr. Smith said hello. Mrs. Johnson agreed.',
#         2, "Abbreviations that should be protected"),
#
#        # Mixed content
#        ('Visit <a href="site.com" title="My.Site">my website</a>. Dr. Smith recommended it.',
#         2, "Mixed XML and abbreviations"),
#
#        # Complex real-world example
#        ('Please say <phoneme alphabet="ipa" ph="ˈhɛ.loʊ">hello</phoneme> to <phoneme alphabet="ipa" ph="ˈwɜːr.ld">world</phoneme>. This is a second sentence.',
#         2, "Multiple phoneme tags"),
#         
#        ('hello <mstts:express-as style="cheerful" styledegree="2"> That wouldd be just amazing! </mstts:express-as> there', 1, "real scenario")
#    ]
#
#    print("Testing sentence splitter with comprehensive edge cases:\n")
#    print("Format: ✓ = Pass, ❌ = Fail, ⚠ = Unexpected but possibly valid\n")
#
#    all_passed = True
#
#    for i, (test_input, expected_sentences, description) in enumerate(test_cases, 1):
#        print(f"Test {i}: {description}")
#        print(f"Input: {test_input}")
#        print(f"Expected sentences: {expected_sentences}")
#
#        try:
#            result = split_sentences(test_input, min_sentence_len=5)
#            actual_sentences = len(result)
#
#            if actual_sentences == expected_sentences:
#                print("✓ PASS")
#            else:
#                print(f"❌ FAIL - Got {actual_sentences} sentences, expected {expected_sentences}")
#                all_passed = False
#
#            print(f"Actual output ({actual_sentences} sentences):")
#            for j, (sent, start, end) in enumerate(result):
#                print(f"  {j+1}: '{sent}' (pos {start}-{end})")
#
#        except Exception as e:
#            print(f"❌ ERROR: {e}")
#            all_passed = False
#
#        print("-" * 80)
#
#    print(f"\nOverall result: {'✓ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
#    return all_passed
#
## Test with your problematic input
#if __name__ == "__main__":
#    print("Starting sentence splitter tests...")
#    test_input = 'I say, <phoneme alphabet="ipa" ph="ˈpi.kæn">pecan</phoneme>.'
#    result = test_sentence_splitter()
#    print(f"\nDirect test result: {split_sentences(test_input)}")
