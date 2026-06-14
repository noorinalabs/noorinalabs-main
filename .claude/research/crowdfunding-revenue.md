# Crowdfunding / Recurring-Revenue Options for NoorinALabs

**Research spike — 2026-06-14**
**Author:** CrowdfundingSpike (research agent, team `noorinalabs`)
**Scope:** Pure research. No code, no repo changes. Evaluate funding avenues to cover modest operating costs (single Hetzner VPS + domain + light infra) for a **nonprofit building open computational tools for Islamic scholarly research** (hadith / isnad analysis platform).

> **Verification note:** Fees and eligibility below are drawn from current platform docs and 2026 comparison sources. Pricing/eligibility tiers change and several platforms (notably LaunchGood) describe fees differently in marketing vs. checkout. Every figure marked **(verify)** should be confirmed by the owner against the platform's own current docs before any public commitment.

---

## TL;DR — Recommended Shortlist

For a small Islamic-scholarship nonprofit with low operating costs and an open-source codebase, the realistic stack is:

1. **LaunchGood** — audience-fit donor base (Muslim ummah), sadaqah-jariyah framing, campaign + recurring giving. Best for reaching the *mission-aligned* donor.
2. **GitHub Sponsors (org) + Open Collective (fiscal host)** — native fit for the open-source identity; Open Collective's fiscal host (Open Source Collective, a US 501(c)(6)) removes the need to register our own nonprofit and gives transparent public ledger accounting — itself a trust signal.
3. **Direct recurring donations via Stripe (+ optionally PayPal)** — a "Support us" button on the landing page; lowest fees, full control, but requires our own legal entity / merchant setup and we build the donate flow.

**The gating decision is legal-entity status** (see § Owner Decisions). Most of the *better* options (charity processing rates, PayPal Giving Fund 0-fee, GitHub Sponsors org payouts, foundation grants) require either a registered 501(c)(3)/equivalent **or** a fiscal host standing in for one. Until that's resolved, the project can only run *individual*-tier campaigns (higher effective cost, weaker trust framing).

---

## Avenue-by-Avenue Comparison

### A. Islamic / Ummah-Oriented Platforms

#### A1. LaunchGood — *primary audience fit*
The largest crowdfunding platform built specifically for Muslims; campaigns are screened in a Muslim community context (no haram-linked campaigns), so a hadith/isnad research tool is squarely on-mission for this donor base.

- **Fees:** Markets "**Zero Platform Fees**." In practice LaunchGood uses a GoFundMe-style model — an *optional* donor tip / voluntary platform contribution at checkout, **plus** payment-processing fees. The historical figure (~5% optional support + ~2.9%+$0.30 processing) is **(verify)** against current checkout.
- **Recurring vs one-time:** Supports both campaign (one-time/launch) and recurring monthly giving — the "how it works" page didn't enumerate recurring details, so confirm the monthly-giving product directly **(verify)**.
- **Nonprofit requirement:** It's a *facilitator*, not a charity — both nonprofits and individuals can run campaigns. No 501(c)(3) strictly required to *start*, but verified-nonprofit status affects payout/trust **(verify)**.
- **Audience fit:** Highest of any option. Donors arrive already motivated by sadaqah-jariyah intent.
- **Integration effort:** Low — hosted campaign page + outbound link/button from landing page. No engineering.

#### A2. Waqf / Sadaqah-Jariyah recurring-giving model (framing, not a platform)
Sadaqah Jariyah ("ongoing charity") is theologically a form of *waqf* (endowment): reward continues as long as the benefit persists. An open, permanent scholarly research tool maps cleanly onto this — "your monthly support keeps this knowledge resource alive." This is a **framing/positioning** layer applied on top of whichever platform we choose (especially LaunchGood recurring, or our own Stripe recurring), not a separate processor. Some orgs run formal Sharia-compliant invested-waqf pools; that is **out of scope** for our budget/complexity but the *language* is high-leverage for the Muslim audience.

#### A3. Muslim-donor foundations / grants
Muslim philanthropic foundations and family offices fund ummah-benefiting digital/educational infrastructure. This is relationship-driven, not a platform — lower priority than A1 for near-term operating costs, but worth a parallel low-effort outreach track once we have a credible public presence and (ideally) charity status. **(verify specific funders)**

### B. Open-Source / Project-Sustainability Platforms

#### B1. GitHub Sponsors — *native open-source fit*
- **Fees:** **0% from personal-account sponsors** (100% passes through). **Up to ~6% from organization sponsors** (3% card processing + 3% GitHub service fee); the 3% card fee is avoidable via invoiced billing, but the 3% service fee remains. **(verify)**
- **Recurring vs one-time:** Both (monthly tiers + one-time).
- **Eligibility:** Any org/individual contributing to open source in a supported region. **Org payouts require a bank account or a fiscal host** — this is where Open Collective pairs in.
- **Audience fit:** Strong for the developer/open-source community; weak for lay Muslim donors.
- **Integration effort:** Very low — `FUNDING.yml` sponsor button appears directly in the GitHub repo; link from landing page.

#### B2. Open Collective + Open Source Collective (fiscal host) — *removes need to self-incorporate*
- **What it is:** A transparent-ledger funding platform. **Open Source Collective (OSC)** is a US-registered **501(c)(6)** nonprofit fiscal host supporting 2,500+ OSS projects — it can hold funds on our behalf so we don't have to register our own nonprofit to receive/spend money cleanly.
- **Fees:** Fiscal host fees typically **5–15%** depending on host (OSC's own rate **(verify)**), on top of payment processing. If a host charges no host fee, Open Collective charges them a 15% platform share — but for *us as a Collective*, the relevant cost is OSC's host fee **(verify)**.
- **Recurring vs one-time:** Both.
- **Nonprofit requirement:** **None on our side** — that's the whole point; OSC is the fiscal/legal umbrella.
- **Audience fit:** Open-source/tech donors; the public transparent ledger is a *trust* asset for any audience.
- **Integration effort:** Low–medium (set up Collective, apply to OSC host, add donate link). Adds public expense transparency for free.

#### B3. Patreon
- **Fees:** Platform fee by tier — **Lite ~5%**, **Pro ~8%**, **Premium ~12%**, **plus** processing (~2.9%+$0.30). Expensive at scale. **(verify)**
- **Recurring:** Yes (membership-first model).
- **Fit:** Built for *perks/membership communities* (exclusive content). Weak fit — we want unrestricted donations, not a perk treadmill, and it's the priciest recurring option.

#### B4. Ko-fi
- **Fees:** Free plan = **0% on tips, 5% on memberships** + processing; **Ko-fi Gold (~$6/mo flat)** drops platform fees to **0%** (you keep ~everything minus Stripe/PayPal processing). **(verify)**
- **Recurring:** Yes (memberships) + one-time tips + shop.
- **Fit:** Excellent low-cost option; the flat-fee Gold model is dramatically cheaper than Patreon at any meaningful volume. Light-touch, simple donate page. Less "nonprofit" branded than Open Collective but very low overhead.

#### B5. Liberapay
- **Fees:** Nonprofit platform — **no platform fee**; creators pay only Stripe/PayPal processing. **(verify)**
- **Recurring:** Recurring-donation-first by design.
- **Fit:** Cheapest recurring option philosophically aligned with FOSS. But **no storefront, no perks, smaller reach** — a pure recurring-donation pipe. Good as a *secondary* link for FOSS-purist donors.

#### B6. Tidelift / sustainability funds
Tidelift pays maintainers of *widely-depended-on* packages via enterprise subscriptions. Our repos are application/platform code, not broadly-consumed libraries — **not a fit** unless we publish a popular reusable package. Note for the record; not actionable now.

### C. General Platforms

#### C1. Stripe (direct recurring donations) — *lowest-fee, full control*
- **Fees:** Standard **2.9% + $0.30**; **501(c)(3) discount ~2.2% + $0.30** (requires >80% of volume be tax-deductible donations). **(verify)**
- **Recurring:** Yes (Stripe Billing / Payment Links / Checkout subscriptions).
- **Requirement:** Our own merchant account + legal entity. We build the donate flow (Stripe Payment Links need almost no code; a custom flow needs engineering).
- **Fit:** Best economics and control; "Support us" button straight on the Astro landing page. Trade-off: we own compliance, receipts, and donor management.

#### C2. PayPal (direct / Giving Fund)
- **Fees:** Standard nonprofit **charity rate ~1.99% + $0.49**; **PayPal Giving Fund covers 100% of processing for enrolled charities** (donor's full amount reaches us). Both require confirmed 501(c)(3). **(verify)**
- **Recurring:** Yes.
- **Fit:** Strong *if* we hold charity status (Giving Fund 0-fee is the best economics of any option). Higher flat fee hurts on small donations vs Stripe. Good to offer *alongside* Stripe for donor choice.

#### C3. GoFundMe (one-time / launch)
- **Fees:** **2.9% + $0.30**; **verified-charity rate 2.2% + $0.30**. **(verify)**
- **Recurring:** Primarily one-time campaign model.
- **Fit:** Mass-market reach for a launch/appeal, but **LaunchGood is strictly better for our audience** (same model, Muslim donor base, mission-screened). Skip in favor of A1.

#### C4. Kickstarter / Indiegogo (one-time launch, all-or-nothing-ish)
- **Fees:** Kickstarter **~8% + $0.20**/txn; Indiegogo **~5% platform + 3–5% processing**. **(verify)**
- **Fit:** Built for *product/reward* launches with deliverables, not ongoing nonprofit operating costs. **Not a fit** for recurring opex.

#### C5. Foundation / academic grants — *largest non-dilutive upside, slow*
- **NEH Office of Digital Humanities** — Digital Humanities Advancement Grants fund software/infrastructure at all project stages, **up to ~$325k**, deadlines ~January. Free/open-source tooling is explicitly in scope. **(verify current cycle)**
- **Andrew W. Mellon Foundation** — actively funds Islamicate/Arabic-Persian digitization and open-source tooling (e.g., the **OpenITI / AOCP** project — directly adjacent to our domain). High strategic fit. **(verify)**
- **NEH–Mellon Fellowships for Digital Publication** — joint program, deadlines ~April. **(verify)**
- **Requirement:** Generally a US nonprofit / academic-institution affiliation or fiscal sponsor; competitive, multi-month timelines.
- **Fit:** Doesn't pay the VPS bill *this month*, but the OpenITI/Mellon adjacency is a genuine strategic match worth a dedicated outreach track. Best pursued once we have charity/fiscal-host status and a public artifact to point to.

#### C6. Notable nonprofit-specific freebie surfaced in research
- **Zeffy** — markets **100% free** donation forms / crowdfunding / memberships for nonprofits (revenue from optional donor tips). Worth evaluating as a zero-fee donate-form layer **if** we have nonprofit status. **(verify model + eligibility)**

---

## "Support Us" Landing-Page Presence — what credible looks like

A trustworthy nonprofit ask, tuned for both the Muslim and open-source audiences:

1. **Cost transparency.** State plainly what we run on ("a single server + domain + modest infra") and roughly what it costs/month. Small, honest numbers build more trust than vague appeals. Open Collective's public ledger (B2) gives this for free if we adopt it.
2. **Sadaqah-jariyah framing** (for the Muslim audience). Position recurring support as ongoing charity that keeps a permanent knowledge resource alive — explicitly invoke sadaqah jariyah / waqf-of-knowledge language. This is the single highest-leverage copy choice for donor resonance.
3. **Open-source framing** (for the developer audience). "Free and open forever — funded by the community." Link GitHub Sponsors / Open Collective.
4. **Choice of method + recurring default.** Offer one mission-aligned platform link (LaunchGood) + one low-fee direct option (Stripe/Ko-fi), with monthly as the default/encouraged tier.
5. **Where the money goes.** One line: "100% covers hosting and infrastructure for open hadith research." Concrete > abstract.
6. **Low-effort v1:** a static "Support" page with outbound buttons (no payment code in our app) → upgrade to embedded Stripe Payment Link later. Avoids PCI/compliance surface initially.

---

## Owner Decisions / Prerequisites

**The legal-entity question gates everything else — decide this first.**

1. **Entity path — pick one:**
   - (a) **Fiscal host** (e.g., Open Collective / Open Source Collective): fastest, no incorporation, gives us legal umbrella + transparent ledger; costs ~5–15% host fee **(verify OSC rate)**. *Recommended starting point.*
   - (b) **Register our own nonprofit / 501(c)(3)-equivalent:** unlocks charity processing rates, PayPal Giving Fund (0-fee), direct grant eligibility, Stripe nonprofit discount — but is slow, has filing/compliance overhead, and depends on our jurisdiction (owner location unknown to me — **needs owner input**).
   - (c) **Individual/unincorporated for now:** can run LaunchGood/Ko-fi/Stripe-standard today, but loses charity rates, Giving Fund, and grant eligibility, and is a weaker trust story.

2. **Jurisdiction of the org / owner** — determines which nonprofit framework and which platforms' charity tiers even apply. I do not have this; **owner must supply.**

3. **Confirm all fee/eligibility figures marked (verify)** against each platform's live docs before any public claim — especially LaunchGood's effective take (marketing says "zero fees" but checkout differs) and OSC's host-fee rate.

### Top open questions for the owner
1. **What is the org's legal status and jurisdiction today** — registered nonprofit, in-progress, or just a personal project? (Gates charity rates, Giving Fund, grants, fiscal-host choice.)
2. **Fiscal host vs. self-incorporate** — is the owner willing to use Open Collective/OSC as a fiscal umbrella (fast, transparent, ~5–15% fee) rather than register our own nonprofit?
3. **Audience priority** — optimize first for the **Muslim donor** (LaunchGood + sadaqah-jariyah framing) or the **open-source community** (GitHub Sponsors + Open Collective)? This drives which "Support us" presence we build first. (They're complementary, but v1 effort should lead with one.)

---

## Sources
- [LaunchGood — How It Works](https://www.launchgood.com/how-it-works)
- [LaunchGood Review 2026 (HalalWallet)](https://www.halalwallet.us/blog/launchgood-review-2026)
- [Open Source Collective](https://opencollective.com/opensource) · [Open Collective — What is Fiscal Hosting](https://opencollective.com/fiscal-hosting) · [Setting Fiscal Host Fees](https://documentation.opencollective.com/fiscal-hosts/setting-up-a-fiscal-host/setting-your-fiscal-host-fees)
- [GitHub Docs — About sponsorships, fees, and taxes](https://docs.github.com/en/sponsors/sponsoring-open-source-contributors/about-sponsorships-fees-and-taxes) · [Setting up GitHub Sponsors for your organization](https://docs.github.com/en/sponsors/receiving-sponsorships-through-github-sponsors/setting-up-github-sponsors-for-your-organization)
- [Ko-fi Fees 2026 (KnowYourCut)](https://knowyourcut.com/blog/kofi-fees-2026) · [Patreon vs Ko-fi 2026 (Full Stack Creators)](https://fullstackcreators.com/patreon-vs-ko-fi-which-creator-membership-platform-wins-in-2026/)
- [Stripe for Nonprofits (Zeffy)](https://www.zeffy.com/blog/stripe-for-nonprofits) · [PayPal Nonprofit Fees 2026 (Zeffy)](https://www.zeffy.com/blog/paypal-donation-fees-for-nonprofits)
- [GoFundMe / Kickstarter / Indiegogo fee comparison (tiing.co)](https://www.tiing.co/blog/crowdfunding/crowdfunding-fees-platform-compared/) · [Best crowdfunding platforms for nonprofits (Zeffy)](https://www.zeffy.com/blog/best-crowdfunding-platforms-nonprofits)
- [NEH — What Grant Program Fits My Digital Project](https://www.neh.gov/blog/what-grant-program-fits-my-digital-project) · [Mellon Persian/Arabic digitization grant (UMD)](https://research.umd.edu/news/mellon-grant-funds-continuation-persian-and-arabic-digitization-project)
- [What is Sadaqah Jariyah (Zakat.org)](https://www.zakat.org/what-is-sadaqah-jariyah-charity-ever-flowing) · [International Waqf Fund — Sadaqah Jariyah](https://waqf.org/sadaqah-jariyah/)
