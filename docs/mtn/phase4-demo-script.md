# Phase 4 demo — MTN Document Assistant (10 minutes)

A stakeholder demo of Office document generation in the MTN Employee AI Assistant. Everything
uses **synthetic data**: the dev model providers (NVIDIA, Groq) are not MTN-approved, so never
type or upload real MTN information during the demo.

**What the audience should take away:** employees ask in plain language and get an MTN-branded
Word, PowerPoint or Excel file in the chat. Every file is built from approved templates and
checked before it is delivered, can be revised without losing the original, and is private to the
person who created it.

---

## Before the demo (10 minutes, the day before)

1. Stack up: `docker compose up -d`, then confirm `docker ps` shows `LibreChat`, `office-mcp`
   (healthy), `rag_api`, `vectordb`, `chat-mongodb` and `chat-meilisearch`.
2. Open `http://localhost:3080` in a normal window and sign in as the **presenter** account.
   New chats open on **MTN Document Assistant** (NVIDIA Nemotron 3 Ultra).
3. Open a **private window** and sign in as a **second account** (any synthetic local account,
   e.g. one you register at `/register`; dev registration is on). Leave that window aside.
4. Have `mtn/demo/Synthetic-Portal-Pilot-Results.pdf` ready on the desktop (regenerate it with
   `mtn/demo/make_demo_pdf.py` if missing). It is a fictional 2-page pilot report.
5. Do one warm-up prompt (step 1 below) and delete that chat, so the first live turn is not the
   slowest.
6. **Fallback:** if NVIDIA is slow or down, pick **MTN Document Assistant (Groq fallback)** from
   the model menu. Groq's free tier can refuse the closing sentence after a tool call for
   rate limits; the file is still attached.

Expect about **25–35 s per document turn** on NVIDIA; most of it is the model writing the content,
about 3–5 s is building and checking the file.

---

## The demo

### 0:00 — Opening (30 s)

> "This is the MTN Employee AI Assistant. Today I'll show the document assistant: it turns a
> request into an MTN-branded Office file using approved templates. Everything you'll see uses
> made-up data."

Point out the **MTN Document Assistant** label, the **MTN Office** and **File Search** chips and
the three suggestions under the welcome text.

### 0:30 — Word: a two-page process document (2 min)

Type exactly:

```
Create a two-page Word document explaining an IT incident process.
```

While it works, say: "It writes the content, then the document service builds the file from the
MTN incident-report template and checks it: it reopens the file, renders it, and confirms it is
two pages before it's delivered."

When the file card appears: open it. Show the MTN logo, the cover table, numbered steps, the
branded table, and "Page 1 of 2" in the footer.

### 2:30 — PowerPoint from a PDF (2 min)

Click **+** → **From Local Computer**, choose `Synthetic-Portal-Pilot-Results.pdf`, then type:

```
Create a five-slide presentation summarising the attached PDF
```

Say: "It only uses figures from the attached report. Every slide is checked for text that would
overflow or overlap before the deck is delivered."

Open the deck: title slide in MTN black and yellow, a table of results by journey, key messages,
and speaker notes.

### 4:30 — Revision without losing the original (1 min 30 s)

In the **same chat**, type:

```
Shorten slide 2 and add a risks table to slide 5
```

Say: "This creates version 2. Version 1 is kept unchanged, so nobody loses the original."
Open both file cards side by side: slide 2 is shorter and slide 5 now has a risks table.

### 6:00 — Excel with live formulas (1 min 30 s)

New chat (top-left pencil), then type:

```
Create an Excel action tracker with 8 synthetic IT actions: owner, due date, a status dropdown, a days-overdue formula, filters, highlighting for blocked items and a chart of actions by status.
```

Open the workbook: use a column filter, change a Status with the dropdown, and show the chart and
the status counts update. Say: "Formulas are recalculated and checked for errors such as #DIV/0!
before the file is delivered."

### 7:30 — Ask questions about a document (File Search) (1 min)

New chat. Click **+** → **More upload options** → **Upload for File Search**, choose the same PDF,
then type:

```
Using the attached report: what was the customer satisfaction score for the SIM swap request journey, and how much did calls for it fall?
```

Expected answer: **4.1 out of 5** and a **12%** fall in calls. Say: "It searches the document
rather than guessing; the answer comes from the report."

### 8:30 — Another user can't see my files (1 min)

Switch to the **private window** (second account):

1. Open the account menu (avatar, bottom left) → **My Files**: the presenter's Word, PowerPoint
   and Excel files are **not listed**. (In the presenter window the same menu lists them.)
2. Say: "Each file belongs to the person who asked for it. Even with a direct link, another
   employee gets 'not found'. The document service also refuses another user's document IDs."

(Optional, technical audiences: in the presenter window copy a file's download link from the file
card's menu, paste it into the private window: it does not download.)

### 9:30 — Close (30 s)

> "Next steps: MTN-approved templates and an MTN-approved model provider, single sign-on in Phase
> 2, and hosting on MTN infrastructure in Phase 3."

---

## Reset after the demo

- Delete the demo chats in both windows (the files go with them per retention settings).
- Sign out of the second account in the private window.

## If something goes wrong

| Symptom | What to do |
|---|---|
| Red "failed" line under *Running mtn-office*, then a file arrives | Normal: the assistant fixed its own input and retried. Mention the checks. |
| "The provider declined this request for exceeding a rate or spending limit" | The file is usually already attached. Wait a minute, or switch to the other model spec. |
| No file card after ~60 s | Check `docker ps` (office-mcp healthy) and retry in a new chat. |
| File Search answer is vague | Make sure the PDF was added with **Upload for File Search** and the File Search chip is on. |
