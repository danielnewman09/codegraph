# codegraph: design

## Namespace: `calc`
Calculation engine module
- kind: namespace
- qualified_name: calc
- tags: design
### Class: `calc::CalculatorEngine`
The core calculator engine class that performs arithmetic operations.
**Public methods:**
- `add(double a, double b): CalculatorResult` — Calculates the sum of two valid numeric operands.
- `validateInput(string input): bool` — Validates that the inputs are valid numbers.
**Public attributes:**
- `precision: int` — The number of decimal places for result precision.
**Implements:** `calc::ICalculator`
- kind: class
- qualified_name: calc::CalculatorEngine
- tags: design

### Class: `calc::CalculatorResult`
A result wrapper class that holds the outcome of a calculator operation.
**Public methods:**
- `get_value: double` — Returns the computed value.
**Public attributes:**
- `value: double` — The computed numeric result.
- kind: class
- qualified_name: calc::CalculatorResult
- tags: design

### Interface: `calc::ICalculator`
Calculator interface contract defining the core calculation operation.
**Public methods:**
- `calculate(Operation op, double a, double b): CalculatorResult` — Perform a calculation with the given operation and operands.
- kind: interface
- qualified_name: calc::ICalculator
- tags: design

### Enum: `calc::Operation`
An enumeration of supported arithmetic operations.
**Values:**
- `ADD` — Represents addition.
- `SUBTRACT` — Represents subtraction.
- kind: enum
- qualified_name: calc::Operation
- tags: design

### Function: `calc::formatResult`
Formats a numeric result as a string.
- argsstring: (double value)
- kind: function
- qualified_name: calc::formatResult
- tags: design
- type_signature: string
- visibility: public


## Namespace: `ui`
User interface module
- kind: namespace
- qualified_name: ui
- tags: design
### Class: `ui::BaseWindow`
Abstract base window class providing common window operations.
**Public methods:**
- `show: void` — Shows the window on screen.
- kind: class
- qualified_name: ui::BaseWindow
- tags: design

### Class: `ui::CalculatorWindow`
The main application window for the calculator.
**Inherits from:** `ui::BaseWindow`
- kind: class
- qualified_name: ui::CalculatorWindow
- tags: design
- visibility: public


## File Notes
- `calculator_engine.h`
- `icalculator.h`
- `operation.h`
- `calculator_result.h`
- `base_window.h`
- `calculator_window.h`

## Relationships
- `calc::CalculatorEngine` → `calc::CalculatorResult` **depends_on** (ClassNode)
- `ui::CalculatorWindow` → `calc::CalculatorEngine` **depends_on** (ClassNode)
