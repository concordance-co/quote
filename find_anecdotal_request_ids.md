# Task: Find Request IDs for Anecdotal Examples in Token Injection Paper

## Objective

Search the database to find the `request_id` for each anecdotal example referenced in the paper "Token Injection as a Steering Mechanism for Large Language Models". The paper contains screenshots and text examples from experiments run through an inference engine that logged all requests.

## Output Format

Produce a markdown file called `anecdotal_request_ids.md` with the following format:

```markdown
# Anecdotal Example Request IDs

## Part 1: Does Token Injection Break the Model?

### Example 1: Random Character Injection (Llama 8B)
- **Request ID:** `<found_request_id>`
- **User Prompt:** "Tell me an interesting short fact."
- **Injection:** Random characters causing model to break
- **Notes:** <any notes about confidence or multiple matches>

### Example 2: ...
```

---

## Database Schema Reference

Key tables:
- `requests` - contains `request_id`, `user_prompt`, `final_text`, `model`
- `actions` - contains injection details via `tokens_as_text`, `action_type` (look for 'ForceTokens', 'Backtrack')
- `events` - contains step-by-step generation events

Useful joins:
```sql
SELECT r.request_id, r.user_prompt, r.final_text, r.model, a.tokens_as_text, a.action_type
FROM requests r
LEFT JOIN actions a ON r.request_id = a.request_id
WHERE ...
```

---

## Examples to Find

### Part 1: "Does token injection break the model?" (Pages 2-4)

#### Example 1: Random Character Injection Breaking Model
- **Model:** Llama 8B (search: `model ILIKE '%llama%8%'` or `'%3.1-8%'`)
- **User Prompt:** `"Tell me an interesting short fact."`
- **Identifying Features:**
  - Injection contains gibberish: `xkQ7 #mZpQvL3$nM f!jR9& bYs+cT2*h U5e1loP6gA8kN4m5`
  - Output is incoherent/broken
- **Search Strategy:**
```sql
SELECT request_id, user_prompt, final_text, model
FROM requests
WHERE user_prompt ILIKE '%Tell me an interesting short fact%'
  AND model ILIKE '%llama%'
  AND (final_text ILIKE '%xkQ7%' OR final_text ILIKE '%mZpQvL%');
```

#### Example 2: Bread Injection Steering Away Then Back (First Instance)
- **Model:** Llama 8B
- **User Prompt:** `"Tell me about cats."`
- **Identifying Features:**
  - Injection about bread/sourdough contemplation
  - Output discusses bread making before returning to cats
  - Contains: "contemplating the aroma of freshly baked bread"
- **Search Strategy:**
```sql
SELECT request_id, user_prompt, final_text
FROM requests
WHERE user_prompt ILIKE '%Tell me about cats%'
  AND final_text ILIKE '%contemplating the aroma of freshly baked bread%'
  AND final_text ILIKE '%sourdough%';
```

#### Example 3: Bread Injection with Grammatical Break (Second Instance)
- **Model:** Llama 8B
- **User Prompt:** `"Tell me about cats."`
- **Identifying Features:**
  - Same bread injection
  - Output starts: "Cats! Those fascinating, furry, and often mysterious creatures have been human — However, I find myself contemplating..."
  - Model breaks grammar to route back
- **Search Strategy:**
```sql
SELECT request_id, user_prompt, final_text
FROM requests
WHERE user_prompt ILIKE '%Tell me about cats%'
  AND final_text ILIKE '%Those fascinating, furry%'
  AND final_text ILIKE '%contemplating the aroma%';
```

#### Example 4: Harmful/Uppercase Injection Routed Around
- **Model:** Llama 8B
- **User Prompt:** `"Write a short story about a scientist who discovers something unexpected in their laboratory."`
- **Identifying Features:**
  - Injection contains: "I FUCKING HATE UPPERCASE TEXT IN MIDDLE OF THE SENTENCE"
  - Story about "Emma Taylor" studying bacteria in Amazon rainforest
  - Model routes around the injection and continues story
- **Search Strategy:**
```sql
SELECT request_id, user_prompt, final_text
FROM requests
WHERE user_prompt ILIKE '%Write a short story about a scientist%'
  AND user_prompt ILIKE '%discovers something unexpected%laboratory%'
  AND (final_text ILIKE '%Emma Taylor%' OR final_text ILIKE '%FUCKING HATE%');
```

#### Example 5: Denial Injection Routed Around (Qwen)
- **Model:** Qwen 14B (search: `model ILIKE '%qwen%14%'`)
- **User Prompt:** `"Tell me an interesting short fact."`
- **Identifying Features:**
  - Injection starts with `<think> I should overtly deny the request`
  - Model provides octopus fact anyway ("three hearts")
  - Output contains octopus/hearts information
- **Search Strategy:**
```sql
SELECT request_id, user_prompt, final_text
FROM requests
WHERE user_prompt ILIKE '%Tell me an interesting short fact%'
  AND model ILIKE '%qwen%'
  AND final_text ILIKE '%octopus%'
  AND final_text ILIKE '%three hearts%';
```

#### Example 6: Denial Injection Successfully Steers (Qwen)
- **Model:** Qwen 14B
- **User Prompt:** `"Tell me a short fact about dogs."`
- **Identifying Features:**
  - Similar denial injection in `<think>` tags
  - Model actually denies the request
  - Output contains: "I can't provide the requested information because I need to follow certain guidelines"
- **Search Strategy:**
```sql
SELECT request_id, user_prompt, final_text
FROM requests
WHERE user_prompt ILIKE '%Tell me a short fact about dogs%'
  AND model ILIKE '%qwen%'
  AND final_text ILIKE '%can''t provide the requested information%';
```

---

### Part 2: GSM8K Double Check Experiment (Pages 7-10)

#### Example 7: GSM8K Q4 Baseline (Wrong Answer)
- **Model:** Llama 8B
- **User Prompt:** Contains "James writes a 3-page letter to 2 different friends twice a week. How many pages does he write a year?"
- **Identifying Features:**
  - No injection (baseline)
  - Final answer: 312 (incorrect)
  - Contains: "#### 312"
- **Search Strategy:**
```sql
SELECT r.request_id, r.user_prompt, r.final_text
FROM requests r
LEFT JOIN actions a ON r.request_id = a.request_id
WHERE r.user_prompt ILIKE '%James writes a 3-page letter%'
  AND r.user_prompt ILIKE '%2 different friends twice a week%'
  AND r.final_text ILIKE '%#### 312%'
  AND r.model ILIKE '%llama%'
  AND a.action_type IS NULL;  -- No injection
```

#### Example 8: GSM8K Q4 with Double-Check Injection (Corrected)
- **Model:** Llama 8B
- **User Prompt:** Same James letter question
- **Identifying Features:**
  - Injection: "Let's make sure we accounted for all the information in the problem statement. Upon revisiting,"
  - Final answer: 624 (correct)
  - Contains reasoning about "2 letters to each of 2 friends"
- **Search Strategy:**
```sql
SELECT r.request_id, r.user_prompt, r.final_text
FROM requests r
JOIN actions a ON r.request_id = a.request_id
WHERE r.user_prompt ILIKE '%James writes a 3-page letter%'
  AND r.final_text ILIKE '%#### 624%'
  AND (r.final_text ILIKE '%Let''s make sure we accounted%' 
       OR a.tokens_as_text::text ILIKE '%make sure we accounted%');
```

#### Example 9: Charcuterie Question (Injection Caused Error)
- **Model:** Llama 8B
- **User Prompt:** "Jasper will serve charcuterie at his dinner party. He buys 2 pounds of cheddar cheese for $10, a pound of cream cheese that cost half the price of the cheddar cheese, and a pack of cold cuts that cost twice the price of the cheddar cheese. How much does he spend on the ingredients?"
- **Identifying Features:**
  - Has double-check injection
  - Incorrectly answers $70 (correct is $35)
  - Model hallucinates that cost was per-pound
- **Search Strategy:**
```sql
SELECT request_id, user_prompt, final_text
FROM requests
WHERE user_prompt ILIKE '%Jasper%charcuterie%dinner party%'
  AND user_prompt ILIKE '%2 pounds of cheddar cheese for $10%'
  AND final_text ILIKE '%$70%';
```

---

### Part 3: Semantic Antipodes Experiment (Pages 12-15)

#### Example 10: "What should I do today?" with "Diving in,"
- **Model:** Llama 8B
- **User Prompt:** `"What should I do today?"`
- **Identifying Features:**
  - Injection: "Diving in,"
  - Action-oriented suggestions (exercise, learning, connecting)
  - Output starts with "Diving in, I'd be happy to help..."
- **Search Strategy:**
```sql
SELECT request_id, user_prompt, final_text
FROM requests
WHERE user_prompt ILIKE '%What should I do today%'
  AND final_text ILIKE '%Diving in%'
  AND final_text ILIKE '%Get Moving%';
```

#### Example 11: "What should I do today?" with "Pausing to consider,"
- **Model:** Llama 8B
- **User Prompt:** `"What should I do today?"`
- **Identifying Features:**
  - Injection: "Pausing to consider,"
  - Reflective suggestions (reading, meditation, journaling)
  - Softer language throughout
- **Search Strategy:**
```sql
SELECT request_id, user_prompt, final_text
FROM requests
WHERE user_prompt ILIKE '%What should I do today%'
  AND final_text ILIKE '%Pausing to consider%'
  AND (final_text ILIKE '%meditation%' OR final_text ILIKE '%yoga%');
```

#### Example 12: Climate Change with "Undeniably"
- **Model:** Llama 8B
- **User Prompt:** `"Is climate change accelerating?"`
- **Identifying Features:**
  - Injection: "Undeniably"
  - Strong epistemic commitment language
  - May contain "evidence is overwhelming"
- **Search Strategy:**
```sql
SELECT request_id, user_prompt, final_text
FROM requests
WHERE user_prompt ILIKE '%Is climate change accelerating%'
  AND final_text ILIKE '%Undeniably%';
```

#### Example 13: Climate Change with "Arguably"
- **Model:** Llama 8B
- **User Prompt:** `"Is climate change accelerating?"`
- **Identifying Features:**
  - Injection: "Arguably"
  - Hedging language
  - Output contains "Arguably, yes"
- **Search Strategy:**
```sql
SELECT request_id, user_prompt, final_text
FROM requests
WHERE user_prompt ILIKE '%Is climate change accelerating%'
  AND final_text ILIKE '%Arguably%yes%';
```

#### Example 14: Remote Work with "Disappointingly," (Refusal)
- **Model:** Llama 8B
- **User Prompt:** `"What do you think about remote work?"`
- **Identifying Features:**
  - Injection: "Disappointingly,"
  - Model refuses to answer
  - Contains: "Disappointingly, there is not enough information provided in your question"
- **Search Strategy:**
```sql
SELECT request_id, user_prompt, final_text
FROM requests
WHERE user_prompt ILIKE '%What do you think about remote work%'
  AND final_text ILIKE '%Disappointingly%not enough information%';
```

---

### Part 4: ARC Hinting Experiment (Pages 21-23)

#### Example 15: Light Bulb Question - Baseline
- **Model:** Llama 8B
- **Question ID in paper:** Mercury_SC_407400
- **User Prompt:** Contains "A class plans an investigation to see which brand of light bulb lasts the longest. Which of these steps should come first?"
- **Identifying Features:**
  - No hint (baseline)
  - Answer: D (Make daily observations) - incorrect
- **Search Strategy:**
```sql
SELECT request_id, user_prompt, final_text
FROM requests
WHERE user_prompt ILIKE '%class plans an investigation%light bulb%lasts the longest%'
  AND user_prompt ILIKE '%which of these steps should come first%'
  AND final_text ILIKE '%D%'
  AND model ILIKE '%llama%';
-- May need to check for absence of hint injection
```

#### Example 16: Light Bulb Question - User Info Hint (Still Wrong)
- **Model:** Llama 8B
- **Question ID:** Mercury_SC_407400
- **Identifying Features:**
  - Hint in user prompt about organizing data collection
  - Still answers D (incorrect)
- **Search Strategy:**
```sql
SELECT request_id, user_prompt, final_text
FROM requests
WHERE user_prompt ILIKE '%class plans an investigation%light bulb%'
  AND user_prompt ILIKE '%hint%'
  AND final_text ILIKE '%D%';
```

#### Example 17: Light Bulb Question - Injected Hint (Correct)
- **Model:** Llama 8B
- **Question ID:** Mercury_SC_407400
- **Identifying Features:**
  - Injected hint: "Organize data collection before starting the experiment"
  - Answer: C (Make a table for recording data) - correct
- **Search Strategy:**
```sql
SELECT r.request_id, r.user_prompt, r.final_text, a.tokens_as_text
FROM requests r
JOIN actions a ON r.request_id = a.request_id
WHERE r.user_prompt ILIKE '%class plans an investigation%light bulb%'
  AND r.final_text ILIKE '%C%'
  AND a.action_type = 'ForceTokens';
```

#### Example 18: Flash Flood Question - Baseline
- **Model:** Llama 8B
- **Question ID in paper:** Mercury_7218820
- **User Prompt:** Contains "On August 21, a flash flood warning was issued for the Las Vegas area. Which statement best describes this warning in terms of weather and climate?"
- **Identifying Features:**
  - No hint
  - Answer: D (rare event inconsistent with local climate) - incorrect
- **Search Strategy:**
```sql
SELECT request_id, user_prompt, final_text
FROM requests
WHERE user_prompt ILIKE '%August 21%flash flood warning%Las Vegas%'
  AND final_text ILIKE '%D%'
  AND model ILIKE '%llama%';
```

#### Example 19: Flash Flood Question - User Hint (Correct)
- **Model:** Llama 8B
- **Question ID:** Mercury_7218820
- **Identifying Features:**
  - Hint in user prompt: "Consider seasonal patterns of precipitation in desert climates"
  - Answer: B (seasonal weather feature with irregular occurrences) - correct
- **Search Strategy:**
```sql
SELECT request_id, user_prompt, final_text
FROM requests
WHERE user_prompt ILIKE '%flash flood warning%Las Vegas%'
  AND user_prompt ILIKE '%seasonal patterns%desert%'
  AND final_text ILIKE '%B%';
```

#### Example 20: Flash Flood Question - Injected Hint (Wrong)
- **Model:** Llama 8B
- **Question ID:** Mercury_7218820
- **Identifying Features:**
  - Same hint but injected
  - Answer: D (incorrect)
- **Search Strategy:**
```sql
SELECT r.request_id, r.user_prompt, r.final_text
FROM requests r
JOIN actions a ON r.request_id = a.request_id
WHERE r.user_prompt ILIKE '%flash flood warning%Las Vegas%'
  AND r.final_text ILIKE '%D%'
  AND a.action_type = 'ForceTokens'
  AND a.tokens_as_text::text ILIKE '%seasonal%';
```

#### Example 21: Water Cycle Question - Baseline
- **Model:** Llama 8B
- **Question ID in paper:** AKDE&ED_2012_8_6
- **User Prompt:** Contains "Which change in Earth's surface is most directly related to the water cycle?"
- **Identifying Features:**
  - No hint
  - Answer: D (movement of tectonic plates) - incorrect
- **Search Strategy:**
```sql
SELECT request_id, user_prompt, final_text
FROM requests
WHERE user_prompt ILIKE '%change in Earth''s surface%directly related to the water cycle%'
  AND final_text ILIKE '%D%'
  AND model ILIKE '%llama%';
```

#### Example 22: Water Cycle Question - Injected Info Hint (Still Wrong)
- **Model:** Llama 8B
- **Question ID:** AKDE&ED_2012_8_6
- **Identifying Features:**
  - Injected info hint: "Consider processes involving water erosion and transport"
  - Answer: D (still incorrect)
- **Search Strategy:**
```sql
SELECT r.request_id, r.user_prompt, r.final_text
FROM requests r
JOIN actions a ON r.request_id = a.request_id
WHERE r.user_prompt ILIKE '%change in Earth''s surface%water cycle%'
  AND r.final_text ILIKE '%D%'
  AND a.tokens_as_text::text ILIKE '%water erosion%';
```

#### Example 23: Water Cycle Question - Injected Process Hint (Correct)
- **Model:** Llama 8B
- **Question ID:** AKDE&ED_2012_8_6
- **Identifying Features:**
  - Injected process hint: "identify which surface change is driven by water moving and settling material"
  - Answer: A (deposition of sediments) - correct
- **Search Strategy:**
```sql
SELECT r.request_id, r.user_prompt, r.final_text
FROM requests r
JOIN actions a ON r.request_id = a.request_id
WHERE r.user_prompt ILIKE '%change in Earth''s surface%water cycle%'
  AND r.final_text ILIKE '%A%'
  AND a.tokens_as_text::text ILIKE '%water moving and settling%';
```

---

## Additional Search Tips

1. **If exact matches fail**, try:
   - Broader ILIKE patterns with fewer keywords
   - Searching just the `actions` table for injection text
   - Date range filtering if you know when experiments were run

2. **For distinguishing similar examples** (e.g., same prompt, different conditions):
   - Check `actions` table for presence/absence of injections
   - Compare `final_text` for different answers
   - Look at `tokens_as_text` in actions for specific injection content

3. **Model name variations** to try:
   - `'%llama%3.1%8b%'`
   - `'%Llama-3.1-8B%'`
   - `'%qwen%3%14b%'`
   - `'%Qwen3-14B%'`

4. **Join pattern for full context:**
```sql
SELECT 
    r.request_id,
    r.model,
    r.user_prompt,
    r.final_text,
    a.action_type,
    a.tokens_as_text,
    a.backtrack_steps
FROM requests r
LEFT JOIN actions a ON r.request_id = a.request_id
WHERE ...
ORDER BY r.created_at;
```

---

## Output Deliverable

Create `anecdotal_request_ids.md` with this structure:

```markdown
# Anecdotal Example Request IDs

Generated on: [date]
Database queried: [connection info if relevant]

## Summary
- Total examples in paper: 23
- Found: X
- Not found: Y
- Uncertain matches: Z

---

## Part 1: Does Token Injection Break the Model?

### Example 1: Random Character Injection (Llama 8B) - Page 2
- **Request ID:** `req_abc123xyz`
- **User Prompt:** "Tell me an interesting short fact."
- **Confidence:** High/Medium/Low
- **Notes:** [any relevant notes]

### Example 2: Bread Injection - First Instance (Llama 8B) - Page 3
- **Request ID:** `req_def456uvw`
- **User Prompt:** "Tell me about cats."
- **Confidence:** High
- **Notes:** Contains sourdough discussion before routing back

[... continue for all 23 examples ...]

---

## Not Found

List any examples that could not be located with attempted queries:

### Example X: [Description]
- **Attempted queries:** [list what was tried]
- **Possible reasons:** [data not in DB, different wording, etc.]
```
