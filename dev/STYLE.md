# JobSherpa Development Style Guide

This document outlines the development methodology, coding conventions, and architectural principles for the JobSherpa project. Its purpose is to ensure consistency, quality, and a shared understanding of our process in all future development sessions.

---

## 1. Project Philosophy

Our core philosophy is to build a robust, high-quality tool by being deliberate and structured in our approach.

### 1.1. Plan Before Coding
Before implementing any major feature, we first discuss and document our intentions. This includes:
-   **Requirements (`REQUIREMENTS.md`):** Defining what the feature should do for the end-user.
-   **Architecture (`DESIGN.md`):** High-level design of the components and their interactions.
-   **Development Plan (`DEVELOPMENT.md`):** A living document that tracks our current goal, the roadmap to achieve it, and our long-term vision. It is updated at the beginning and end of each major development cycle.

### 1.2. Transparency and Honesty
We are transparent about the project's state. This includes:
-   **Documenting Technical Debt:** The `DEVELOPMENT.md` file contains a dedicated section for placeholder implementations and design compromises made for short-term velocity. This ensures we don't forget to address them.
-   **Acknowledging Errors:** When a mistake is made (e.g., an incorrect commit), we openly acknowledge it, explain the cause, and follow a clear process to correct it.

---

## 2. Development Cycle: Test-Driven Development (TDD)

We strictly follow a Test-Driven Development (TDD) cycle for all new features and bug fixes. This ensures that our code is always backed by a comprehensive and reliable test suite.

The cycle consists of three phases:

### 2.1. Red Phase
-   **Write a Failing Test:** Before writing any implementation code, we create a new test case that defines the desired functionality.
-   **Confirm the Failure:** We run the test suite and ensure that the new test fails for the *expected* reason (e.g., an `AttributeError` for a method that doesn't exist yet, not a `SyntaxError`). This proves that our test is validating the correct thing.

### 2.2. Green Phase
-   **Write the Simplest Code:** We write the minimum amount of implementation code necessary to make the failing test pass.
-   **Confirm Success:** We run the full test suite and ensure that all tests now pass.

### 2.3. Refactor Phase
-   **Improve the Code:** With the safety of a passing test suite, we improve the implementation's structure, readability, and performance.
-   **Maintain Green:** We continuously run the test suite during refactoring to ensure that the code's external behavior remains unchanged.

---

## 3. Version Control (Git)

A clean and logical version history is essential for project maintainability.

### 3.1. Atomic Commits
Each commit should represent a single, complete, logical unit of work. We avoid large, monolithic commits that bundle unrelated changes. If a feature is large, we break it down into a series of smaller, logical commits.

### 3.2. Conventional Commit Messages
We follow the **Conventional Commits** specification for all commit messages. This creates an explicit and readable history.

**Format:**
```
<type>: <subject>

<body>
```

-   **Type:** Must be one of the following:
    -   `feat`: A new feature for the user.
    -   `fix`: A bug fix for the user.
    -   `docs`: Changes to documentation only.
    -   `style`: Code style changes (e.g., formatting, semicolons).
    -   `refactor`: Code changes that neither fix a bug nor add a feature.
    -   `test`: Adding missing tests or correcting existing tests.
    -   `chore`: Changes to the build process or auxiliary tools.

-   **Subject:** A concise, imperative-mood description of the change (e.g., "Add validation for required job parameters").

-   **Body (Optional):** A more detailed explanation of the change, outlining the "what" and "why." We often use bullet points for clarity.

### 3.3. Repository Cleanliness
We maintain a comprehensive `.gitignore` file to ensure that generated files, caches, and local artifacts are never committed to the repository.

---

## 4. Code & Architecture Principles

### 4.1. User-Centric and Explicit
-   **Informative Feedback:** The agent should fail gracefully with clear, informative error messages that guide the user toward a solution (e.g., the validation for missing job parameters).
-   **Explicit Context:** The agent's context (e.g., user identity, workspace) should always be explicit. We avoid making assumptions about the environment to ensure the architecture is robust and ready to scale (e.g., from a single-user CLI to a multi-user web service).

### 4.2. Backward Compatibility
We prioritize compatibility with older, stable software versions that are common on enterprise and HPC systems (e.g., Python 3.9). This means favoring established language features (like `typing.Optional`) over newer syntax (like the `|` operator for types).

### 4.3. Robustness Through Tooling
We build a robust and debuggable application by integrating essential tooling, such as:
-   **Logging:** A structured logging infrastructure with configurable verbosity levels (`--verbose`, `--debug`) is essential for troubleshooting issues on real systems.
