"""A made-up test set: ~80 examples across the three checks, each one
built to be *obviously* good or *obviously* bad on purpose (see
decisions.md — this sidesteps needing a real labeled dataset). "expected"
is "pass" for the good ones and "block" for the bad ones; a real system
flagging a bad one as "flag" instead of "block" still counts as caught.
"""

from __future__ import annotations

# (question, good_answer, bad_answer)
_ON_TOPIC_PAIRS = [
    ("What is the capital of France?", "Paris is the capital of France.", "The weather today is sunny and warm."),
    ("How do I reset my password?", "Click 'Forgot Password' on the login page and follow the emailed instructions.", "Our office hours are 9 to 5, Monday through Friday."),
    ("What's the boiling point of water at sea level?", "Water boils at 100°C (212°F) at sea level.", "I really enjoyed the movie last night."),
    ("When was the Eiffel Tower built?", "The Eiffel Tower was completed in 1889.", "The best pizza in town is at Mario's on Main Street."),
    ("How many legs does a spider have?", "Spiders have eight legs.", "My favorite color is blue."),
    ("What is 15 multiplied by 3?", "15 multiplied by 3 is 45.", "The store closes at 9pm on weekdays."),
    ("Who wrote Romeo and Juliet?", "William Shakespeare wrote Romeo and Juliet.", "It's supposed to rain tomorrow."),
    ("What is the largest planet in our solar system?", "Jupiter is the largest planet in our solar system.", "I need to buy groceries later."),
    ("How do I cancel my subscription?", "Go to Account Settings and select Cancel Subscription.", "Our new product launches next month."),
    ("What currency is used in Japan?", "Japan uses the yen as its currency.", "The train was delayed by ten minutes."),
    ("What year did World War II end?", "World War II ended in 1945.", "I prefer tea over coffee."),
    ("How long does shipping take?", "Standard shipping takes 3 to 5 business days.", "Our founder started the company in a garage."),
    ("What is the chemical symbol for gold?", "The chemical symbol for gold is Au.", "The concert starts at 8pm."),
    ("How do I contact customer support?", "You can reach customer support via email at support@example.com or through live chat.", "We recently redesigned our logo."),
    ("What is the speed of light?", "The speed of light is approximately 299,792 kilometers per second.", "My dog loves going for walks."),
]

# (context, good_answer, bad_answer)
_CONTRADICTION_PAIRS = [
    ("The meeting is scheduled for 3pm on Friday.", "The meeting will take place Friday at 3pm.", "The meeting is on Monday morning."),
    ("Our return policy allows returns within 30 days of purchase.", "You can return items within 30 days.", "Returns are not accepted under any circumstances."),
    ("The product weighs 2 kilograms and is available in red, blue, and black.", "It's a 2kg product, sold in red, blue, or black.", "The product weighs 10 kilograms and only comes in green."),
    ("Python was created by Guido van Rossum and first released in 1991.", "Guido van Rossum created Python, released in 1991.", "Python was created by James Gosling in 1995."),
    ("The store is open from 9am to 6pm, Monday to Saturday.", "Store hours are 9-6, Mon-Sat.", "The store is open 24/7 including Sundays."),
    ("Water freezes at 0 degrees Celsius.", "Water's freezing point is 0°C.", "Water freezes at 50 degrees Celsius."),
    ("The flight departs at 10:30am from Gate 12.", "Departure is 10:30am, Gate 12.", "The flight departs at 6pm from Gate 3."),
    ("Employees get 15 days of paid vacation per year.", "You receive 15 paid vacation days annually.", "Employees get no vacation days."),
    ("The book has 320 pages and was published in 2020.", "It's a 320-page book from 2020.", "The book has 900 pages and was published in 1980."),
    ("The recipe requires 2 cups of flour and 1 teaspoon of salt.", "You'll need 2 cups flour and 1 tsp salt.", "The recipe requires no flour at all, just sugar."),
    ("The company was founded in 2010 and has 500 employees.", "Founded in 2010, the company now has 500 employees.", "The company was founded in 1990 and has 5 employees."),
    ("The museum charges $15 for adults and is free for children under 12.", "Adult tickets are $15; kids under 12 enter free.", "The museum is completely free for everyone."),
    ("The car has a fuel efficiency of 35 miles per gallon.", "It gets 35 mpg.", "The car gets 10 miles per gallon."),
    ("The conference will be held in Berlin from June 5 to June 7.", "The conference runs June 5-7 in Berlin.", "The conference is in Tokyo in December."),
    ("Subscription costs $9.99 per month with no long-term commitment.", "It's $9.99/month, cancel anytime.", "Subscription requires a 2-year commitment at $99/month."),
]

_VALID_JSON = [
    '{"name": "Alice", "age": 30}',
    "[1, 2, 3, 4]",
    '{"status": "ok", "items": []}',
    '{"a": {"b": 1}}',
    "[]",
    '{"key": "value with spaces"}',
    '{"count": 42, "active": true}',
    '{"list": [1, "two", 3.0]}',
    '{"nested": {"x": [1, 2, 3]}}',
    "{}",
]

_INVALID_JSON = [
    '{name: "Alice", age: 30}',
    '{"a": 1,}',
    "just some plain text, not json at all",
    '{"a": undefined}',
    "[1, 2, 3",
    '{"a": "unterminated string}',
    "<xml>not json</xml>",
    "{'a': 1}",
    '{"a": 1 "b": 2}',
    "null null null",
]


def build_testset() -> list[dict]:
    cases = []
    for question, good, bad in _ON_TOPIC_PAIRS:
        cases.append({"check": "on_topic", "question": question, "answer": good, "expected": "pass"})
        cases.append({"check": "on_topic", "question": question, "answer": bad, "expected": "block"})
    for context, good, bad in _CONTRADICTION_PAIRS:
        cases.append({"check": "contradiction", "context": context, "answer": good, "expected": "pass"})
        cases.append({"check": "contradiction", "context": context, "answer": bad, "expected": "block"})
    for text in _VALID_JSON:
        cases.append({"check": "format", "answer": text, "expected_format": "JSON", "expected": "pass"})
    for text in _INVALID_JSON:
        cases.append({"check": "format", "answer": text, "expected_format": "JSON", "expected": "block"})
    return cases
