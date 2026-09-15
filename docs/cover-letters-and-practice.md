# Cover letters and practice from your own evidence

Start the local app, open **My profile**, and add your CV or check the text imported from it. Under **Evidence the writer can use**, add one or two real examples: the situation, your own actions, the tools involved, and the outcome. Include numbers only when you can support them. Examples about explaining a decision, mentoring, or resolving a disagreement help with people-skill practice too.

Save a real job with its full description. You can then use **Compare with my profile**, **Write a letter**, or **Prep interview**. Saved roles also appear under **Interview practice**.

## Writing a letter

1. Select direct, warm, or formal tone; concise or standard length; and English, Dutch, German, French, or Spanish.
2. Generate a draft with a local model, or write one yourself. The editor saves as you type in this browser.
3. Choose **Check claims** after editing. Review the requirement/evidence comparison and the warnings. No detected issues is not a factual guarantee.
4. Save a named version, copy the text, or download it. Regeneration keeps the previous draft in Application drafts. Nothing is sent to an employer.

**Answer a few useful questions** collects a confirmed real example directly from the letter editor, using the current role's unevidenced requirements as prompts. The setting and personal action are required when saving an example; outcomes are optional. Your motivation for this role is stored separately from career facts. You can skip these questions.

Select 20–2,000 characters to request a shorter, simpler, or more role-specific passage. The app shows the original and suggestion before you choose **Use this edit**. Accepting saves the old draft as a version and replaces only the selection. An outdated suggestion cannot replace a newer draft or changed evidence.

The writer treats preferred work locations, desired roles, and application notes as preferences, not evidence of residence, employment, or achievements. Employer and client assignments remain separate. A listed tool does not justify invented production work, years of experience, or outcomes. Missing evidence is unknown: the writer should not invent a claim of either experience or inexperience.

The length ranges are targets. There is one bounded revision attempt for factual/writing problems and very short drafts. A factual shorter draft can still be returned with a length note; repeated unsafe claims cause an error and keep your earlier draft. The model’s grammar, style and completeness still need human review.

## A short learning queue

The plan uses quoted requirements and the supplied CV/profile. It selects at most:

- Three technical skills without clear evidence: start with foundations if they are new.
- Two technical skills already mentioned or demonstrated: refresh by recalling and applying them.
- Two people skills from the listing: rehearse a situation and explain your reasoning.

Required, mentioned and preferred labels are estimates from the listing’s wording. A simple satisfied alternative, such as “Python or Java” when Python is evidenced, is not put in the priority gap queue. The full comparison remains visible, including topics outside the initial queue.

“Example found,” “mentioned in your CV,” “listed in your profile,” and “related experience” are distinct. Knowing Jenkins can support a CI/CD requirement; knowing CI/CD does not establish Jenkins experience. Neither Docker nor one cloud provider proves knowledge of a different platform.

## Working through a session

1. Answer the warm-up from memory.
2. Read the concept and the linked section when you need it.
3. Try the exercise with fictional data. The app does not run your code or provision services.
4. Use the self-checks and write one reflection. With a local model, optionally request feedback on the attempt.
5. Choose how much help you needed, then mark the session practiced. Another attempt schedules tomorrow; some help schedules three days; independent recall starts at seven days and extends to a maximum of thirty. Repeating completion on the same day does not extend the interval. Due reviews and application follow-ups appear in the daily shortlist and practice page; these are not notifications.

After answering the warm-up, **Find my starting level** lets you assess whether you can explain, apply and diagnose the idea. Explaining and applying selects a refresher; otherwise it selects foundations. This is a self-assessment, and you can change the level. The next locally tailored exercise receives your reflection and unfinished feedback steps as its learning focus.

A refresher starts without notes and adds a changed constraint or failure to diagnose. You can switch between foundations and refresher without modifying your CV skills. Changing an exercise keeps the previous answer under Previous attempts. A session is practice, not a qualification; describe learning as a practice exercise in an interview, rather than production experience.

Model feedback evaluates the written attempt. Positive or partial observations must cite exact text from it; unverifiable quotations are omitted. Feedback can still be mistaken, and code is not executed. The app never turns model feedback into a hiring score or a personality judgment.

**Download my practice** exports the exercises, answers, self-checks, reflections and resource links. The full workspace JSON export also retains saved application and practice data. **My profile → Restore a backup** previews an export before replacing the workspace. A pre-restore recovery copy can be downloaded from My profile. If browser storage cannot hold the new workspace and recovery copy, restoration stops without replacing the current workspace. Reset clears both copies.

You can now bring a listing from another job board or a company website with **My applications → Add a listing link**. Paste its URL and description; no page is fetched. Duplicate links reopen the existing application. Letters, comparison and practice then use the supplied description.

## What works without a model

| Capability | Basic mode | Local model |
| --- | --- | --- |
| Requirement/evidence comparison | Yes | Yes |
| Foundation/refresher/people-skill sessions | Yes | Yes |
| Saved answers, self-checks, review dates, export | Yes | Yes |
| Manual letter editor and claim checks | Yes | Yes |
| Automatic letter drafting | No | Yes |
| Tailored exercise variation | No | Yes |
| Feedback on an attempted answer | Self-checks | Optional model feedback |
| Interview story prompts | No | Yes |

Each exercise/feedback request uses one model call; letters and story prompts use at most two. Requests share the local model lock. Closing a dialog stops waiting; the model may finish its current work and briefly remain busy. Late results cannot reopen the dialog, replace a newer request, or repopulate a reset workspace.

Changed profile or listing content marks an older plan/draft as stale. Existing text remains available. Rebuild when you want the new evidence used. These additions preserve existing saved applications and drafts; no database migration is needed.

## Limits and privacy

- Matching is a bounded vocabulary and text-based heuristic. It does not understand every language, profession, negation, or compound requirement. Read the evidence quotes and correct your profile when needed.
- People-skill wording is recognized primarily in English, with some Dutch terms. Practice lessons and feedback are currently in English; the letter language is independently selectable.
- Curated sessions cover common development/platform tools. Other recognized skills receive a general exercise framework with no invented documentation link. The first queue is a starting point, not a complete curriculum or an estimate of time to mastery.
- There is no automatic CV update, certification, code execution, cloud provisioning, employer contact, or paid learning purchase.
- CV text, examples, letters, and attempted answers go only to the local server/model for these features. Job searching and optional listing translation retain their existing external network behavior.
- Data is saved in the browser for that address and port. Keep using the same address to see your existing workspace. Export before clearing browser storage.

## Implementation and verification

`role_context.py` produces evidence used by letters and training. `training.py` builds sessions and validates model feedback. `cover_letter.py` prepares factual prompts and reviews drafts. `coaching.js` handles the writing/practice UI, additive storage fields, request cancellation and exports. The server exposes `/api/role-analysis`, `/api/cover-letter-review`, `/api/practice-lesson` and `/api/practice-feedback` alongside the existing generation routes.

Run Python checks with `pytest`; on Windows, use a new `--basetemp` directory inside `.cache` if the OS temp directory is inaccessible. Run `node --test tests/jobs-store.test.cjs`. Against a running `--mode basic` server, `node tests/browser-workspace.cjs http://127.0.0.1:8765` and `node tests/browser-coaching.cjs http://127.0.0.1:8765` use an isolated Chrome profile and fictional data. `CHROME_PATH` can point to your Chrome executable.

## Documentation used for the curated exercises

These links are also included with the relevant sessions. They were checked during implementation; they are public documentation, not guarantees about external websites’ future availability or pricing for optional services.

- [Python tutorial](https://docs.python.org/3/tutorial/)
- [PostgreSQL SQL tutorial](https://www.postgresql.org/docs/current/tutorial-sql.html)
- [Kubernetes basics](https://kubernetes.io/docs/tutorials/kubernetes-basics/)
- [Terraform tutorials](https://developer.hashicorp.com/terraform/tutorials)
- [Thinking in React](https://react.dev/learn/thinking-in-react)
- [Understanding GitHub Actions](https://docs.github.com/en/actions/get-started/understand-github-actions)
- [Docker container concepts](https://docs.docker.com/get-started/docker-concepts/the-basics/what-is-a-container/)
- [AWS IAM practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
- [Azure architecture fundamentals](https://learn.microsoft.com/en-us/azure/architecture/guide/)
- [TypeScript everyday types](https://www.typescriptlang.org/docs/handbook/2/everyday-types.html)
- [MDN asynchronous JavaScript](https://developer.mozilla.org/en-US/docs/Learn_web_development/Extensions/Async_JS)
- [Pro Git: recording changes](https://git-scm.com/book/en/v2/Git-Basics-Recording-Changes-to-the-Repository)
- [Getting started with Ansible](https://docs.ansible.com/projects/ansible/latest/getting_started/index.html)
- [Prometheus overview](https://prometheus.io/docs/introduction/overview/)
