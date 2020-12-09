def ordered_items_in_text(to_verify: list, text: str) -> bool:
    """Return if all items in list appear in order in text.

    Examples:
      ordered_items_in_text(['a', '1'], 'ab1')  # Returns True
      ordered_items_in_text(['1', 'a'], 'ab1')  # Returns False
    """
    index = 0
    for item in to_verify:
        index = text[index:].find(item)
        if index < 0:
            return False
    return True
