![Flowchart](https://user-images.githubusercontent.com/6601700/118792660-dc148b80-b88b-11eb-89e6-3a65df46fcd4.png)

### Explanation of the Two Options:

#### 1. **Taking the survey via Sawtooth**:
   - **Pros**:
     - Sawtooth handles the Conjoint-Based Choice (CBC) logic.
     - Survey data is directly saved in the Sawtooth platform.
   - **Cons**:
     - The respondent's survey must be completed one by one, which can be time-intensive.
     - This approach is prone to errors, when using Selenium.

#### 2. **Scraping once + implementing CBC logic in Python**:
   - **Pros**:
     - Automating responses for multiple personas is very fast after scraping the questions.
     - Fewer errors compared to relying on tools like Selenium.
   - **Cons**:
     - CBC logic must be implemented manually in Python, requiring additional effort.
     - The output is not directly stored in Sawtooth, which might be inconvenient for some research purposes.
