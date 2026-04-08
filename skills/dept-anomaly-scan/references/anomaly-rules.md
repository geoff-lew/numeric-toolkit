# Anomaly Detection Rules

These rules define what constitutes a GL-to-department miscoding. They are split
into two sections: **universal rules** that apply to virtually any company, and
**industry-specific rules** that only apply to certain business models.

Account numbers listed are illustrative examples from common NetSuite charts of
accounts. Always map them to the actual account codes in the workspace before
flagging — the principles are what matter, not the numbers.

## Table of Contents

### Universal Rules
1. [COGS in non-COGS departments](#cogs-in-non-cogs-departments)
2. [Finance & Treasury accounts in non-Finance departments](#finance--treasury-accounts-in-non-finance-departments)
3. [Legal fees outside Legal / Finance](#legal-fees-outside-legal--finance)
4. [Payroll admin outside Finance / HR](#payroll-admin-outside-finance--hr)
5. [Audit & accounting fees outside Finance](#audit--accounting-fees-outside-finance)
6. [Facilities outside G&A](#facilities-outside-ga)
7. [Board expenses outside Executive / G&A](#board-expenses-outside-executive--ga)
8. [Depreciation & amortization in operational departments](#depreciation--amortization-in-operational-departments)
9. [Marketing accounts in Engineering or G&A](#marketing-accounts-in-engineering-or-ga)
10. [Structural Anomalies](#structural-anomalies)
11. [Transaction-Level Red Flags](#transaction-level-red-flags)

### Industry-Specific Rules

#### SaaS & Software
12. [Capitalized software development costs outside R&D / Engineering](#capitalized-software-development-costs-outside-rd--engineering)
13. [SaaS COGS components appearing in G&A or Sales](#saas-cogs-components-appearing-in-ga-or-sales)
14. [Stock-based compensation concentrated in one department](#stock-based-compensation-concentrated-in-one-department)
15. [Customer Success / Professional Services costs in Sales](#customer-success--professional-services-costs-in-sales)
16. [R&D tax credit tracking accounts outside R&D](#rd-tax-credit-tracking-accounts-outside-rd)
17. [Deferred revenue or contra-revenue adjustments in operational departments](#deferred-revenue-or-contra-revenue-adjustments-in-operational-departments)

#### Hardware & Manufacturing
18. [Hardware & Manufacturing (hardware/physical product companies only)](#hardware--manufacturing)

---

## Universal Rules

---

### COGS in non-COGS departments

**Accounts**: Any account under the COGS / Cost of Revenue parent (e.g., 5000–5099
in many NetSuite setups — COGS-Implementation, COGS-Support, Merchant Fees,
Reseller Fees, etc.)

**Expected departments**: A dedicated COGS or Operations department, or no
department (unallocated). Some companies intentionally allocate COGS to entity
level rather than department.

**Flag if found in**: Any Sales & Marketing, R&D, or G&A department

**Why it matters**: COGS in a functional department distorts gross margin by
department and overstates that department's cost burden.

**Common root causes**:
- Month-end allocation journal entries with wrong department tags
- Accrual templates that haven't been updated after a restructuring
- AP team selecting the wrong department on vendor bills for direct costs

**Note**: If COGS regularly appears in a specific department and no one can explain
why, flag for management confirmation — it may be intentional (e.g., a support team
that sits inside a product org).

---

### Finance & Treasury accounts in non-Finance departments

**Accounts**: Bank fees, interest expense, interest income, foreign exchange gains/
losses, loan fees (e.g., 5710 Bank Fees, 7115 Interest Expense, 6105 Interest Income)

**Expected departments**: Finance / Treasury / G&A

**Flag if found in**: Any operational department (Sales, Marketing, Engineering,
Product, Support, etc.)

**Why it matters**: Treasury and banking activity has nothing to do with functional
teams. When it appears in Product Management or Engineering it's almost always a
miscoding.

**Common root causes**:
- Month-end JE with wrong department tags across multiple lines
- Default department on a bank account or clearing account set incorrectly

---

### Legal fees outside Legal / Finance

**Accounts**: Legal Fees (e.g., 5420 in many setups)

**Expected departments**: Legal, Finance, or G&A

**Flag if found in**: Any non-Legal / non-Finance department

**Exception**: Amounts <$1K in other departments may be legitimate (a business unit
paying for a specific contract review). Flag but mark low priority.

**Common root causes**:
- Trademark or IP legal work coded to the department that requested it rather than Legal
- Month-end JE with wrong department hard-coded

---

### Payroll admin outside Finance / HR

**Accounts**: Payroll processing fees, benefits administration fees, HRIS software
costs (e.g., 5425 Payroll Processing Fees)

**Expected departments**: Finance, HR / People Operations, or G&A

**Flag if found in**: Any operational department (Sales, Engineering, Marketing, etc.)

**Why it matters**: Payroll processing is an administrative function. It should never
appear in a revenue-generating or product department — when it does, it inflates that
department's headcount-related costs and distorts efficiency metrics.

**Common root causes**:
- Month-end allocation JE with wrong department assigned to this line
- Payroll vendor bills coded to the department of the person who approved them

---

### Audit & accounting fees outside Finance

**Accounts**: Audit & Accounting Fees (e.g., 5405)

**Expected departments**: Finance, Accounting, or G&A

**Flag if found in**: Any non-Finance department

**Common root causes**: Same as payroll admin — usually a month-end JE miscoding
rather than a deliberate allocation.

---

### Facilities outside G&A

**Accounts**: Rent, utilities, janitorial, common area maintenance, lease costs
(e.g., 5625 Rent, 5630 Repairs & Maintenance, 5640 Telephone/Internet)

**Expected departments**: G&A (typically Finance or a dedicated Facilities/Office
Operations department)

**Flag if found in**:
- Any Sales & Marketing department
- Any Engineering / R&D department (unless it's a dedicated R&D lab with its own
  lease — confirm with management)
- Moving between G&A sub-departments month-over-month (not necessarily wrong, but
  worth confirming — may indicate instability in the department mapping)

**Common root causes**:
- Department mapping adjustments mid-year
- Manual JEs reclassing facility costs to the wrong G&A sub-department

---

### Board expenses outside Executive / G&A

**Accounts**: Board expenses, director fees, board meeting costs (e.g., 5715 Board
Expenses)

**Expected departments**: Executive, CEO Office, or G&A

**Flag if found in**: Any operational department (Engineering, Sales, Marketing, etc.)

**Common root causes**: Month-end JE miscoding — board costs almost never belong
in an operational department.

---

### Depreciation & amortization in operational departments

**Accounts**: Depreciation Expense, Amortization Expense (e.g., 7105, 7110)

**Expected departments**: Finance / Accounting, or unallocated (no department). Some
companies allocate depreciation to the department that owns the asset — if this is
the convention, confirm it's consistent.

**Flag if found in**: Sales, Marketing, or Engineering departments unless those
departments own significant fixed assets and intentional allocation is confirmed.

**Common root causes**:
- Month-end depreciation JE with a default department that wasn't updated
- Allocation template that assigns all depreciation to a single operational department

---

### Marketing accounts in Engineering or G&A

**Accounts**: Any account under the Marketing parent — branding, lead gen,
advertising, PR, content, tradeshows, website, collateral (e.g., 5300–5340)

**Expected departments**: Sales & Marketing

**Flag if found in**:
- Any Engineering / R&D / Product department
- Any G&A department (except: PR under CEO Office may be intentional — flag but
  note it needs management confirmation)

**Common root causes**:
- Department restructuring where a team (e.g., Growth or Developer Relations) moved
  from Marketing to Product but accrual templates weren't updated
- Marketing accrual JEs with wrong department hard-coded

---

## Structural Anomalies

These aren't about specific GL accounts but about patterns in the data:

### New large items ($0 → >$10K)
Any line that was $0 in the prior period but has >$10K in the current period. Signals
a new vendor, a department restructuring, or a miscoding. Always drill into the
transaction lines.

### Extreme variance (>500%)
Any line with >500% month-over-month change where both periods had non-zero balances.
Could be seasonal but is worth checking.

### Offsetting patterns
A GL account disappears from Department A and simultaneously appears in Department B
for a similar amount. Confirm whether the transfer was intentional.

### Cross-entity equal splits
If two or more entities show the exact same dollar amount on an unusual account/
department combination, it's almost certainly a miscoded allocation JE rather than
an organic transaction. Single JEs that allocate costs equally across entities are
a common source of systematic miscodings.

---

## Transaction-Level Red Flags

### Manual journals with vague memos
Journal entries with memos like "Department Review Reclasses" or "Dept mapping
adjustments" that move large amounts. These systematic reclasses may themselves be
creating new anomalies.

### Credit card charges with mismatched descriptions
Ramp/Brex/Amex charges where the memo describes one function but the department tag
is another. Usually means the employee's card default department is wrong in the
expense management system.

### Stale transactions
Credit card charges or vendor bills with transaction dates 2+ months before the
posting date. Late-syncing expenses that may have been coded hastily.

### Round-number journal entries
Large round-dollar amounts (e.g., exactly $100,000 or $50,000) on manual JEs.
These are estimates or accruals often assigned to a placeholder department.

### Accrual reversals creating negatives
Negative amounts on expense accounts in unexpected departments. Often accrual
reversals where the original accrual was in the wrong department, perpetuating
the error.

---

## Industry-Specific Rules

---

### SaaS & Software

*Applies to: SaaS companies, software businesses, subscription-based tech companies.*
*Skip for hardware, manufacturing, or non-tech companies.*

#### Capitalized software development costs outside R&D / Engineering

**Accounts**: Capitalized Internal-Use Software, Capitalized Development Costs (ASC 350-40
or IAS 38 asset accounts, often in the 1xxx or 1800s range)

**Expected departments**: R&D or Engineering (or unallocated — some companies don't
tag an intangible asset account to a department at all)

**Flag if found in**: G&A, Sales & Marketing, or any non-technical department

**Why it matters**: Under ASC 350-40, only costs incurred during the application
development stage and allocated to qualifying engineers can be capitalized. If capitalized
software hits a G&A department, it may signal that the allocation methodology has
broken down or that non-qualifying costs are being improperly capitalized.

---

#### SaaS COGS components appearing in G&A or Sales

**Accounts**: Hosting/cloud infrastructure (AWS, GCP, Azure), third-party API costs,
CDN costs, data processing fees, customer support labor or tooling (e.g., Zendesk,
Intercom SaaS subscriptions used by support teams)

**Expected departments**: COGS, a dedicated Customer Success or Infrastructure
department, or Support

**Flag if found in**: G&A, Finance, or Sales & Marketing

**Why it matters**: Misclassifying hosting and support costs in G&A or Sales
understates cost of revenue and overstates gross margin. This is especially common
when the CFO or IT team pays the AWS bill but doesn't tag it to COGS.

**Common root causes**:
- Cloud infrastructure bills approved by Finance/IT and defaulted to a G&A department
- Support tool subscriptions (Zendesk, Intercom) coded to G&A because the Accounting
  team owns the vendor relationship
- New headcount in Customer Success sitting in a Sales department due to a default
  department on the employee record

---

#### Stock-based compensation concentrated in one department

**Accounts**: Stock-based compensation expense (SBC), equity compensation expense
(typically a sub-account under each functional P&L line, or a single account allocated
to departments)

**Expected departments**: Distributed across all departments in proportion to headcount
and grant levels (Engineering, Sales, G&A, etc.)

**Flag if**: All SBC is concentrated in a single department (especially G&A) when
the company has employees across multiple departments

**Why it matters**: SBC should be allocated to the department of the employee
receiving the grant. If it's all sitting in one place, the allocation JE has a
hard-coded department that was never updated — a systemic error that distorts
departmental P&L for every period.

**Common root causes**:
- Monthly SBC allocation JE uses a single default department rather than a split
- Equity management system (Carta, Shareworks) exports to the GL with a fixed
  department tag

---

#### Customer Success / Professional Services costs in Sales

**Accounts**: Salaries and benefits for CS/implementation teams, CS tool subscriptions,
onboarding and training costs

**Expected departments**: Customer Success, Professional Services, or COGS/Support

**Flag if found in**: Sales & Marketing

**Why it matters**: CS and implementation labor are typically COGS or a distinct
post-sales cost center. When coded to Sales, it inflates the apparent cost of the
Sales department and distorts metrics like CAC and sales efficiency.

**Common root causes**:
- CS headcount defaulted to a Sales department during onboarding
- Shared vendor bills (e.g., a CRM tool used by both Sales and CS) coded entirely
  to Sales

---

#### R&D tax credit tracking accounts outside R&D

**Accounts**: Any account specifically used to track qualifying R&D expenditures for
Section 41 (US) or SR&ED (Canada) credit purposes

**Expected departments**: R&D / Engineering exclusively

**Flag if found in**: G&A, Sales, or any non-technical department

**Why it matters**: Section 41 qualifying research expenses must be allocated to
qualifying research activities. If those accounts appear in non-R&D departments, the
credit calculation may be wrong — and the miscodings may have tax consequences.

---

#### Deferred revenue or contra-revenue adjustments in operational departments

**Accounts**: Deferred revenue recognition JEs, contra-revenue accounts (refunds,
credits, discounts), revenue adjustment accounts

**Expected departments**: No department (balance sheet accounts), or Finance /
Accounting for any P&L-facing adjustment

**Flag if found in**: Sales, Engineering, or any operational department

**Why it matters**: Deferred revenue is a balance sheet account. Revenue adjustment
JEs belong in Finance or Accounting. When these appear in Sales or Engineering it
usually means a revenue recognition or billing adjustment JE was miscoded.

---

### Hardware & Manufacturing

*Applies to: hardware companies, physical product companies, manufacturers.*
*Skip for pure SaaS, services, or financial companies.*

**Accounts**: Hardware development, lab equipment, tooling, manufacturing
development, regulatory/compliance, NPI (e.g., 800xxx–810xxx)

**Expected departments**: R&D (Hardware, Manufacturing Development, Product)

**Flag if found in**:
- Any Sales & Marketing department
- Any G&A department
- COGS (unless it's a direct production cost like reliability testing)

**Common root causes**:
- Employees doing R&D work with a card default department set to Marketing
- Manufacturing vendor bills (contract manufacturers in China, HK, etc.) where AP
  selected the wrong department during bill entry
- Accruals that inherit the wrong department from the original bill

**Typical vendors**: Contract manufacturers (names often containing "HK",
"Shenzhen", "Dongguan"), tooling companies, electronics suppliers, materials vendors.
