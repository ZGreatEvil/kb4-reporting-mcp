# User guide: KnowBe4 chat

*Bahasa Indonesia: [USER_GUIDE.id.md](USER_GUIDE.id.md)*

The KnowBe4 chat answers questions about your organisation's KnowBe4 data in plain language: risk scores, phishing tests, training, people and groups. It can also draw charts, make CSV or Excel files, and give security-awareness guidance from NIST documents.

It **only reads** KnowBe4 data and never changes anything. An AI model running on your own server writes the answers. Your questions and the KnowBe4 data are not sent to any outside AI service.

## Contents

1. [Opening the chat](#1-opening-the-chat)
2. [Asking a question](#2-asking-a-question)
3. [What you can ask](#3-what-you-can-ask)
4. [Periods and comparisons](#4-periods-and-comparisons)
5. [Follow-up questions](#5-follow-up-questions)
6. [Charts and files](#6-charts-and-files)
7. [Reading an answer](#7-reading-an-answer)
8. [Messages you may see](#8-messages-you-may-see)
9. [Good practice](#9-good-practice)

## 1. Opening the chat

1. Open the address your administrator gave you, for example `https://kb4-chat.example.internal`. If a login box appears, sign in with the account you were given.
2. The first time, choose **Bahasa Indonesia** or **English**. The page remembers your choice. Switch at any time with **ID / EN** at the top right.
3. The status label at the top shows whether the service is working:

| Status | Meaning |
|---|---|
| **Online** | Everything is running. |
| **Limited** | Part of the service has a problem; answers may fail. Tell your administrator. |
| **Offline** | The page cannot reach the server. Try again later or tell your administrator. |

## 2. Asking a question

- Type your question and press **Enter** or **Send**. **Shift + Enter** starts a new line.
- While it works, the page shows what it is doing, for example "Fetching data…" or "Writing the answer…". Most answers take 10–60 seconds.
- You can type the next question while one is being answered. Up to 10 wait in a queue, and each answer appears under its own question.
- **New** clears the conversation and starts again. It also stops an answer that is still being written.
- Write naturally. Short, informal and slightly misspelt questions are fine: "risk score now?", "who clicked the last phishing", "training this month how's it going".

If your organisation has more than one KnowBe4 console, name it in the question, for example "risk score of *Subsidiary*". Otherwise the main console is used.

## 3. What you can ask

Type **"what can you do"** at any time for the full list. In short:

| Area | Example questions |
|---|---|
| **Summaries and reports** | "Give me a security summary of our organisation" · "Monthly report for management for October" · "Full report on the Finance group" · "Per manager, whose team is behind on training?" |
| **Risk score** | "What is the risk score now, and why?" · "Who are the 10 riskiest users?" · "Which group is riskiest?" · "Is the IT group getting better or worse?" |
| **Phishing** | "How did the last phishing test go?" · "Who clicked, and who reported it?" · "Phish-prone trend over the last 12 months" · "Which templates fooled the most people?" · "Who failed more than once?" · "Did people fail on phones or laptops?" |
| **Training** | "Training completion of the latest campaign" · "October's campaign per group" · "Who is overdue?" · "Which modules are least finished?" · "Who has never been trained?" |
| **People and groups** | "Find Jane Example" · "Who is in the Finance group?" · "Which departments exist?" · "Who has never signed in to KnowBe4?" · "New joiners this quarter" |
| **Terms** | "What is phish-prone %?" · "What does Past Due mean?" |
| **Licence** | "When does our subscription end, and how many seats are used?" |
| **NIST guidance** | "How can we measure how effective awareness training is?" · "How often should we run phishing simulations?" |

If your organisation uses other KnowBe4 products (PhishER, PasswordIQ, Real-Time Coaching), "what can you do" lists those questions too.

**What it cannot do:**
- change or delete anything in KnowBe4;
- predict future values;
- answer questions outside KnowBe4 and security awareness.

## 4. Periods and comparisons

- **Name a period in the question:** "in October 2026", "the last 3 months", "Q3 2026", "since March", "this year".
- **Without a period, the past 12 months are used.** The answer says which period it covers.
- **Compare two periods:** "phishing this quarter vs last quarter", "training 2026 compared with 2025".
- Some answers are always about **today**, such as current risk scores and group members. When you name a period for one of these, the answer says that it shows the current state.

## 5. Follow-up questions

The chat remembers the last few messages, so you can continue naturally:

- **More rows:** "show more" or "next" after a list.
- **Pick from a list:** reply with the number, for example "2", when it lists several people or campaigns.
- **Refer back:** "why?", "and last quarter?" or "what about him?" after an answer about one person.
- **Ambiguous names:** if a name matches several people, the chat asks which one first.

If an answer goes off track, press **New** and ask again with more detail.

## 6. Charts and files

- **Charts** appear on their own when they help. The chart's numbers are always shown as a table under it too. You can also ask: "chart the risk score over the year".
- **Files** are made only when you ask: "export the overdue people to Excel" or "CSV of October's campaign per person". The link appears in the answer.
- **Files and charts are deleted after one hour.** Download what you need straight away.
- Files can contain names and email addresses. Store and share them as you would any personal data, and only with people who are allowed to see it.

## 7. Reading an answer

Most answers have the same shape:

1. **A bold first line**: the answer itself.
2. **Key facts**: the numbers behind it, often with a table.
3. **Why**: what in the data explains it.

Where a guidance answer uses NIST, the source documents are listed at the end.

KnowBe4 data is reused for 10 minutes to save requests. To get it straight from KnowBe4, say **"fetch fresh data"** or **"refresh"**.

The answers come from an AI model. Checks in the software remove numbers that are not in the data, but the model can still word things loosely now and then. **For decisions or reports to management, check the key numbers in the KnowBe4 console.**

## 8. Messages you may see

| Message (in short) | What to do |
|---|---|
| The daily KnowBe4 request limit has been reached | KnowBe4 limits how many requests can be made in 24 hours. Try again later. Questions asked in the last 10 minutes may still be answered from saved data. |
| KnowBe4 cannot be reached / the key was rejected | Try again in a few minutes. If it continues, tell your administrator. |
| No response for … seconds | Ask a narrower question, for example one group or one month. |
| The question or conversation is too long | Press **New**, or shorten the question (maximum 4,000 characters). |
| Which person do you mean? | Several people match the name. Reply with the number or the full name. |
| This chat only reads KnowBe4 data | You asked it to change something; do that in the KnowBe4 console. |

## 9. Good practice

- **Be specific when it matters:** name the group, campaign, month or person. "Training of the October campaign for Finance" gets a better answer than "training?".
- **One question at a time** gives clearer answers than three questions in one message.
- **Don't paste passwords, API keys or other secrets** into the chat.
- **The answers contain personal data** about colleagues. Use it only for your security-awareness work.
