# Bank Marketing

This directory contains a four-row fixture and a full normalized benchmark snapshot for the UCI `bank-additional-full.csv` variant. The full variant has 41,188 rows and 21 semicolon-delimited fields. The benchmark selects `age`, `job`, `marital`, `duration`, `loan`, and `y`; `duration` is used for the long-call filter because the official `bank-additional-full.csv` has no `balance` field. The other official Bank Marketing variants are different datasets and are not mixed into this contract.

Source: [UCI archive](https://archive.ics.uci.edu/static/public/222/bank%2Bmarketing.zip), DOI `10.24432/C5K306`, CC BY 4.0. Literal `unknown` values remain values; empty fields are the only null representation.
