# Original brief

Kestrel Motor Group: Data & AI Challenge
========================================
The Kestrel Motor Group is an Australian dealership group consisting of 24 dealerships across Victoria, New South Wales and Queensland, selling and servicing several vehicle brands. Each dealership collects customer feedback from sales, service and parts customers and sends it to head office.

The Problem
-----------
Some dealerships send a new file each month or quarter; others keep one running workbook and send that.

Nobody ever agreed on a template. Each site's spreadsheet has evolved over the years, built by whoever happened to own it at the time. Head office has a folder full of these files and cannot answer simple questions about their customers' experience and dealership performance.

The Head of Customer Experience has asked you to help!

Your task
---------
1. **Bring it together.** Consolidate the feedback into a single, clean dataset. Decide what it should look like, and explain why.
2. **Decide what you can trust.** Define data quality and validation rules, apply them, and report what passed, what failed, and what you did about it.
3. **Make sense of the words.** Use AI to turn free-text feedback into something you can analyse, such as themes, sentiment or anything else you think matters. Show how you know whether it worked.
4. **Answer the business.** Tell the Head of Customer Experience:
   - What are the main drivers of negative feedback, and how do they vary across dealerships and departments?
   - Has anything changed over the year?
   - Where should Kestrel focus first, and roughly what is it worth?

### What's in this pack
- **`feedback/`**: 52 spreadsheets (.xlsx and .csv) of customer feedback from the dealerships, covering October 2025 to September 2026
- **`reference/dealerships.csv`**: the official list of dealerships, with codes, regions and brands
- **`reference/monthly_revenue.csv`**: vehicles sold, service jobs, parts transactions and revenue by dealership and month

The files were created by people, not systems. Treat everything you find with healthy suspicion. All names, contact details and businesses are fictional (any resemblance to real persons is purely coincidental), but please handle the personal information as if it were real.

### What technology you can use
**It's your call**, as long as you can explain your choices (and "it's new and I wanted to try it" is a perfectly valid reason). Use any language, any frameworks or libraries, even external services (at your own expense!).

### Can you use AI?
Yes! We expect you'll want to use AI tools, both to help you build (coding agents and assistants) and inside your solution (for example, using an LLM to classify feedback or interpret messy columns). There are no restrictions on which tools you use. We are interested in *how* you use them: what you delegate, what you check, and where you catch them getting it wrong.

### What to submit
Put everything in your repo:
- **Your solution.** Code, notebooks, scripts, etc., in any language or stack. It should be reproducible enough for us to follow what you did.
- **Your report.** A document (`README.md`, or PDF, etc.) covering:
    - Overview of your approach, assumptions, and solution
    - Tech choices and rationale
    - Observations about data quality
    - Answers to the business questions for the Head of Customer Experience
    - Insights and recommendations about the feedback across dealerships
    - AI usage overview: a brief, honest record of how you used AI: key prompts or interactions, where it helped, where it was wrong, and how you verified its output.

Keep it concise - it doesn't have to be an essay; in fact, we'd prefer it wasn't. Bullets and short paragraphs are enough.

### How to submit
Submission as a git repo is preferred, via the platform of your own choosing (github, bitbucket, gitlab, self-host. As long as we can access and clone it).

### What's important
We are **not** assessing code quality or polish. We will look at:
- **Problem solving:** did you understand what the business actually needs?
- **Data analysis:** what did you notice, and how did you handle it?
- **Trust and verification:** how do you know your results, and the AI's output, are right?
- **Insight and communication:** is your answer clear, useful and honest about its limits?
- **AI fluency:** did you use AI tools thoughtfully and effectively?

Good luck and have fun!
