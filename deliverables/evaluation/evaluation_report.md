# Evaluation: AI labels vs hand labels

Hand-labelled rows scored: **120** (sheet rows 120, left blank 0, labelled but no AI label 0). Limits: one labeller, small sample, Noosa (QLD05) not in the sample.

| Measure | Value | 95% CI |
|---|---|---|
| Sentiment accuracy | 96.7% | 91.7% - 98.7% |
| Sentiment Cohen's kappa | 0.95 | |
| Primary theme accuracy | 85.8% | 78.5% - 91.0% |
| Theme accuracy, lenient (AI primary is either human theme, or vice versa) | 96.7% | |
| Primary theme Cohen's kappa | 0.82 | |
| Both theme and sentiment correct | 83.3% | |

## Per theme (primary)

| class | support_human | predicted_ai | precision | recall | f1 |
|---|---|---|---|---|---|
| Staff attitude | 20 | 23 | 0.83 | 0.95 | 0.88 |
| Communication and updates | 38 | 34 | 0.94 | 0.84 | 0.89 |
| Wait time and turnaround | 27 | 29 | 0.79 | 0.85 | 0.82 |
| Price and billing | 14 | 12 | 1.00 | 0.86 | 0.92 |
| Work quality and fix | 14 | 13 | 0.92 | 0.86 | 0.89 |
| Vehicle or product | 0 | 0 |  |  |  |
| Process and facilities | 7 | 9 | 0.56 | 0.71 | 0.63 |
| Other | 0 | 0 |  |  |  |

## Per sentiment

| class | support_human | predicted_ai | precision | recall | f1 |
|---|---|---|---|---|---|
| positive | 61 | 58 | 1.00 | 0.95 | 0.97 |
| neutral | 0 | 1 | 0.00 |  |  |
| negative | 37 | 39 | 0.95 | 1.00 | 0.97 |
| mixed | 22 | 22 | 0.95 | 0.95 | 0.95 |

## Sentiment confusion (rows = human, columns = AI)

| human | positive | neutral | negative | mixed |
|---|---|---|---|---|
| positive | 58 | 1 | 1 | 1 |
| neutral | 0 | 0 | 0 | 0 |
| negative | 0 | 0 | 37 | 0 |
| mixed | 0 | 0 | 1 | 21 |

## Theme confusion (rows = human, columns = AI)

| human | Staff attitude | Communication and updates | Wait time and turnaround | Price and billing | Work quality and fix | Vehicle or product | Process and facilities | Other |
|---|---|---|---|---|---|---|---|---|
| Staff attitude | 19 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| Communication and updates | 2 | 32 | 3 | 0 | 0 | 0 | 1 | 0 |
| Wait time and turnaround | 0 | 1 | 23 | 0 | 0 | 0 | 3 | 0 |
| Price and billing | 1 | 0 | 1 | 12 | 0 | 0 | 0 | 0 |
| Work quality and fix | 0 | 1 | 1 | 0 | 12 | 0 | 0 | 0 |
| Vehicle or product | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Process and facilities | 1 | 0 | 0 | 0 | 1 | 0 | 5 | 0 |
| Other | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## 10 disagreements

`hint` is automatic; `reviewer_reason` is for the human reviewer (see errors.csv).

| feedback_id | dealer_code | department | comment_clean | human_primary | human_secondary | ai_primary | ai_secondary | human_sentiment | ai_sentiment | ai_confidence | hint |
|---|---|---|---|---|---|---|---|---|---|---|---|
| QLD02-a2596b91b4 | QLD02 | Parts | I do not know anything about cars so I just showed the Altura Vista part number on my phone. Price was very fair, I was expecting much worse. But I was on the phone hold for so long I nearly hung up. | Work quality and fix | Communication and updates | Wait time and turnaround | Price and billing | mixed | mixed | 0.8 | different theme |
| NSW07-d74e165500 | NSW07 | Service | CLEAR EXPLANATIONS, LONG WAIT. THAT'S THE SUMMARY. | Communication and updates | Wait time and turnaround | Wait time and turnaround | Communication and updates | mixed | mixed | 0.8 | competing themes: same two themes, different primary |
| VIC05-90fd4cfc4b | VIC05 | Sales | Smooth as. Friendly crew. | Process and facilities | Staff attitude | Staff attitude | Process and facilities | positive | positive | 0.75 | competing themes: same two themes, different primary |
| QLD04-2658a760af | QLD04 | Service | Always a warm welcome here and I never have to chase for news, they just ring or text me. | Communication and updates |  | Staff attitude | Communication and updates | positive | positive | 0.8 | competing themes: same two themes, different primary |
| VIC01-67ae75e890 | VIC01 | Service | Back-ordered part, so we were stuck with a loan car and car seats to shuffle for ages. Then the invoice showed a cleaning fee and a higher parts price than quoted. Bit rich. | Price and billing | Wait time and turnaround | Wait time and turnaround | Price and billing | negative | negative | 0.8 | competing themes: same two themes, different primary |
| VIC01-f941d7fd16 | VIC01 | Service | Bit of a shock, honestly. Usually you hear nothing till you front up at the counter. This time the texts rolled in all day long. | Communication and updates |  | Communication and updates |  | positive | neutral | 0.7 | neutral vs polar |
| NSW02-e4690913a9 | NSW02 | Service | Prompt updates by phone and text. Then the same fault came back on the highway. | Work quality and fix | Communication and updates | Work quality and fix | Communication and updates | mixed | negative | 0.8 | mixed vs single polarity |
| VIC06-3d29b534be | VIC06 | Service | No wait list, no cancellation list, nothing. Just 'ring back next month'. | Wait time and turnaround | Process and facilities | Process and facilities | Communication and updates | negative | negative | 0.6 | competing themes: same two themes, different primary |
| NSW01-50a589d6e1 | NSW01 | Sales | No complaints abuot how easy the purchase was, everything ready when we arrived. The sales pitch for extras in the finance room was too aggressive though, felt like I couldn't get out of there. | Price and billing | Process and facilities | Staff attitude | Process and facilities | mixed | mixed | 0.75 | different theme |
| QLD06-74b9f05ede | QLD06 | Service | RANG TO BOOK, NO AVAILABILITY FOR WEEKS. ASKED TO BE PUT ON A CANCELLATION LIST. NEVER HEARD ANOTHER WORD. (rego [REGO]) | Wait time and turnaround | Process and facilities | Process and facilities | Communication and updates | negative | negative | 0.75 | competing themes: same two themes, different primary |

## Voice tag check (Voice_check tab)

30 rows: agreement 86.7%, staff-tag precision 100.0%, recall 78.9%

## D2 / V1: Ringwood 1-10 score vs AI sentiment

| score | negative | mixed | neutral | positive | n | negative_share | negative_or_mixed_share |
|---|---|---|---|---|---|---|---|
| 1 | 24 | 0 | 0 | 0 | 24 | 1.00 | 1.00 |
| 2 | 15 | 0 | 1 | 0 | 16 | 0.94 | 0.94 |
| 3 | 8 | 2 | 0 | 0 | 10 | 0.80 | 1.00 |
| 4 | 11 | 2 | 0 | 0 | 13 | 0.85 | 1.00 |
| 5 | 4 | 6 | 1 | 0 | 11 | 0.36 | 0.91 |
| 6 | 3 | 15 | 0 | 0 | 18 | 0.17 | 1.00 |
| 7 | 0 | 7 | 0 | 19 | 26 | 0.00 | 0.27 |
| 8 | 0 | 2 | 1 | 18 | 21 | 0.00 | 0.10 |
| 9 | 2 | 0 | 0 | 49 | 51 | 0.04 | 0.04 |
| 10 | 0 | 0 | 0 | 48 | 48 | 0.00 | 0.00 |

- Scores 1-4 negative or mixed: 98.4% (negative only 92.1%); strict definition supported: True
- Negative share at 5: 36.4% (n=11); at 6: 16.7% (n=18)
- Ringwood at-risk share: headline <=5 25.5% vs sensitivity <=6 32.1% (all 321 rated 1-10 rows). The headline rule stays <=5 (D1); the gap is the likely understatement.
- Uses AI sentiment on every labelled Ringwood comment, not only the hand-labelled sample; its reliability is the sentiment accuracy above.
