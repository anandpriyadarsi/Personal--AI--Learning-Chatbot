from personal_learning_assistant.learning_studio.rendering import markdown


def test_only_known_internal_sections_are_links():
    text='[Next](#lesson-2) [missing](#no-such-section) [unsafe](javascript:alert(1)) [outside](https://example.com)'
    rendered=str(markdown(text,section_targets={'lesson-2':'/learning/modules/synthetic/1?view=learn&section=lesson-2'}))
    assert 'href="/learning/modules/synthetic/1?view=learn&amp;section=lesson-2"' in rendered
    assert rendered.count('<a ') == 1
    assert 'javascript:' not in rendered and 'href="https:' not in rendered


def test_markup_and_images_stay_inert():
    result=str(markdown('<script>alert(1)</script> ![asset](https://evil.invalid/image.png)'))
    assert '<script>' not in result and '<img' not in result
