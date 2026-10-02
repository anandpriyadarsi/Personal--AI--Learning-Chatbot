"""Small offline operation cards. Examples use synthetic data, never assessment keys.

NumPy examples assume `import numpy as np`; Pandas `import pandas as pd`;
visualization `import matplotlib.pyplot as plt`. Outputs describe return values
unless print is explicit. The UI never executes these snippets.
"""

# what, why, syntax, input, example, output/behaviour, common mistake
_GROUPS = {
    "Python": [
        ("Variables", "Name a value so you can reuse it.", "name = value", "Any Python value", "score = 8; print(score + 2)", "Prints 10", "= assigns; == compares."),
        ("Datatypes", "Check whether a value is a number, text or collection.", "type(value)", "Any value", "print(type('12').__name__)", "Prints str", "'12' is text, not an integer."),
        ("Type conversion", "Turn numeric text into a number.", "int(text); float(text); str(value)", "Convertible value", "print(int('12') + 3)", "Prints 15", "int('3.5') raises ValueError; use float first if appropriate."),
        ("Lists", "Store an ordered, changeable sequence.", "items = [...]; items.append(value)", "Sequence of values", "a = [2, 4]; a.append(6); print(a)", "Prints [2, 4, 6]; append itself returns None", "Do not write a = a.append(6)."),
        ("Tuples", "Keep an ordered sequence whose items cannot be reassigned.", "items = (a, b)", "Values", "point = (2, 5); print(point[1])", "Prints 5", "A one-item tuple needs a comma: (2,)."),
        ("Dictionaries", "Look up values using meaningful keys.", "d[key]; d.get(key, default)", "Key/value pairs", "d = {'math': 8}; print(d.get('chem', 0))", "Prints 0", "d[missing_key] raises KeyError."),
        ("Sets", "Keep unique values and compare membership.", "set(values); a & b; a | b", "Iterable of hashable values", "print(sorted(set([3, 1, 3])))", "Prints [1, 3]", "Sets are not indexed and have no guaranteed display order."),
        ("Indexing", "Pick one element by position.", "items[index]", "Sequence", "a = [10, 20, 30]; print(a[-1])", "Prints 30", "Indexing starts at 0."),
        ("Slicing", "Take a range of a sequence.", "items[start:stop:step]", "Sequence", "print([0, 1, 2, 3, 4][1:4:2])", "Prints [1, 3]", "The stop index is excluded."),
        ("Conditions", "Choose a branch based on a Boolean test.", "if condition: ...\nelse: ...", "Boolean condition", "x = 7\nif x > 5:\n    print('high')", "Prints high", "Indent the block; use == for equality."),
        ("For loops / range", "Repeat work over items or integer positions.", "for item in iterable: ...", "Iterable", "for i in range(3):\n    print(i)", "Prints 0, 1, 2 on separate lines", "range(3) does not include 3."),
        ("While loops", "Repeat until a condition becomes false.", "while condition: ...", "Condition and changing state", "n = 2\nwhile n > 0:\n    print(n)\n    n -= 1", "Prints 2 then 1", "Update the condition variable to avoid an infinite loop."),
        ("Functions", "Reuse a named block that returns a result.", "def name(parameters):\n    return result", "Arguments", "def square(x):\n    return x * x\nprint(square(3))", "Prints 9", "print displays; return sends a value to the caller."),
        ("Common built-ins", "Count, total or find extremes without a loop.", "len(x); sum(x); min(x); max(x)", "Suitable iterable", "a = [2, 4, 6]; print(len(a), sum(a), max(a))", "Prints 3 12 6", "sum expects numeric values, not numeric strings."),
        ("Sorting", "Put items into a predictable order.", "sorted(items, reverse=False)", "Comparable items", "print(sorted([3, 1, 2]))", "Prints [1, 2, 3]; original list is unchanged", "list.sort() changes the list and returns None."),
        ("Enumerate / zip", "Pair positions with values or combine parallel sequences.", "enumerate(items); zip(a, b)", "Iterables", "print(list(zip(['A', 'B'], [2, 4])))", "Prints [('A', 2), ('B', 4)]", "zip stops at the shortest iterable by default."),
    ],
    "NumPy": [
        ("Array creation", "Store homogeneous numeric data for array operations.", "np.array(values)", "Nested or flat numeric sequence", "a = np.array([1, 2, 3]); print(a.tolist())", "Prints [1, 2, 3]", "Ragged nested rows are not a regular numeric matrix."),
        ("Zeros / ones", "Prepare an array with a chosen shape.", "np.zeros(shape); np.ones(shape)", "Integer or shape tuple", "print(np.ones((2, 2), dtype=int).tolist())", "Prints [[1, 1], [1, 1]]", "Use (rows, columns), not two unrelated arguments."),
        ("Arange / linspace", "Create evenly spaced values.", "np.arange(start, stop, step); np.linspace(start, stop, num)", "Bounds and step/count", "print(np.linspace(0, 1, 3).tolist())", "Prints [0.0, 0.5, 1.0]", "linspace uses a count; arange uses a step and excludes stop."),
        ("Shape", "Read the size of each axis.", "a.shape", "ndarray", "a = np.array([[1, 2, 3], [4, 5, 6]]); print(a.shape)", "Prints (2, 3)", "shape is an attribute; do not call shape()."),
        ("Ndim", "Count axes, not elements.", "a.ndim", "ndarray", "print(np.array([[1, 2]]).ndim)", "Prints 2", "A row matrix has two axes even if it has one row."),
        ("Dtype", "Inspect the type stored in the array.", "a.dtype", "ndarray", "print(np.array([1, 2], dtype=np.int32).dtype)", "Prints int32", "Mixed numeric values may be converted to one shared type."),
        ("Reshape", "Change shape while preserving the number of elements.", "a.reshape(rows, columns)", "Compatible array size", "print(np.arange(6).reshape(2, 3).tolist())", "Prints [[0, 1, 2], [3, 4, 5]]", "The old and new element counts must agree."),
        ("Flatten / ravel", "Convert an array to one dimension.", "a.flatten(); a.ravel()", "ndarray", "print(np.array([[1, 2], [3, 4]]).ravel().tolist())", "Prints [1, 2, 3, 4]; flatten copies, ravel may share data", "Changing a ravel result can change the original when it is a view."),
        ("Array indexing / slicing", "Select cells, rows or columns.", "a[row, col]; a[:, col]", "2D array", "a = np.array([[1, 2], [3, 4]]); print(a[:, 1].tolist())", "Prints [2, 4]", "Basic slices may be views; use copy() for independence."),
        ("Boolean masking", "Keep values satisfying a condition.", "a[condition]", "Array and matching Boolean mask", "a = np.array([1, 4, 7]); print(a[a > 3].tolist())", "Prints [4, 7]", "Use (a > 1) & (a < 7), not Python and."),
        ("Elementwise arithmetic", "Apply arithmetic to corresponding values.", "a + b; a * b; a ** 2", "Compatible arrays", "a = np.array([2, 3]); print((a ** 2).tolist())", "Prints [4, 9]", "a * b is elementwise multiplication, not matrix multiplication."),
        ("Broadcasting", "Combine compatible shapes without a manual loop.", "a + row", "Trailing dimensions equal or 1", "print((np.ones((2, 2), dtype=int) + np.array([2, 3])).tolist())", "Prints [[3, 4], [3, 4]]", "Incompatible shapes cause ValueError; inspect shape first."),
        ("Aggregation", "Summarize many values with one result.", "np.sum(a); np.mean(a); np.min(a); np.max(a)", "Numeric array", "print(np.mean([2, 4, 6]))", "Prints 4.0", "Ordinary mean propagates NaN; nanmean ignores it."),
        ("Axis", "Choose which dimension to reduce.", "a.sum(axis=0); a.sum(axis=1)", "2D array", "a = np.array([[1, 2], [3, 4]]); print(a.sum(axis=0).tolist())", "Prints [4, 6]; rows are reduced, one result per column", "axis=1 reduces columns and gives one result per row."),
        ("Concatenate / stack", "Join arrays along an existing or a new axis.", "np.concatenate([a,b]); np.stack([a,b])", "Compatible arrays", "print(np.stack([[1, 2], [3, 4]]).shape)", "Prints (2, 2); stacking adds an axis", "Concatenating 1D arrays produces a longer 1D array."),
        ("Transpose", "Swap the rows and columns of a matrix.", "a.T", "2D array", "print(np.array([[1, 2, 3]]).T.shape)", "Prints (3, 1)", "Transposing a 1D array does not turn it into a column matrix."),
        ("Dot / matrix product", "Combine vectors or multiply matrices.", "a @ b; np.dot(a, b)", "Matching inner dimensions", "print(np.array([1, 2]) @ np.array([3, 4]))", "Prints 11", "For 2D arrays, (m,n) @ (n,p) gives (m,p)."),
        ("Vector norm", "Measure vector length.", "np.linalg.norm(v)", "Numeric vector", "print(np.linalg.norm([3, 4]))", "Prints 5.0", "Vector length is not the number of elements."),
    ],
    "Pandas": [
        ("Series / DataFrame", "Represent a labelled column or table.", "pd.Series(values); pd.DataFrame(dictionary)", "Values or equal-length columns", "df = pd.DataFrame({'x': [2, 4]}); print(df.shape)", "Prints (2, 1)", "Dictionary columns must have compatible lengths."),
        ("read_csv", "Load a CSV file as a DataFrame.", "pd.read_csv(path)", "CSV path or file-like object", "from io import StringIO\ndf = pd.read_csv(StringIO('x,y\\n1,2\\n')); print(df.shape)", "Prints (1, 2)", "Check delimiter, header and file path if columns look wrong."),
        ("Head / tail", "Inspect the first or last few rows.", "df.head(n); df.tail(n)", "DataFrame", "df = pd.DataFrame({'x': [2, 4, 6]}); print(df.head(2)['x'].tolist())", "Prints [2, 4]", "A small preview does not describe the full dataset."),
        ("Info", "Inspect columns, non-null counts and datatypes.", "df.info()", "DataFrame", "pd.DataFrame({'x': [1, 2]}).info()", "Prints a table summary and returns None", "Do not assign df = df.info()."),
        ("Describe", "Get a quick statistical summary.", "df.describe()", "DataFrame with numeric columns", "df = pd.DataFrame({'x': [2, 4, 6]}); print(df.describe().loc['mean', 'x'])", "Prints 4.0", "By default, numeric summaries do not summarize every text column."),
        ("Shape / columns / dtypes", "Check table dimensions, names and types.", "df.shape; df.columns; df.dtypes", "DataFrame", "df = pd.DataFrame({'x': [1, 2]}); print(df.shape, list(df.columns))", "Prints (2, 1) ['x']", "These are attributes, not methods."),
        ("loc", "Select rows and columns by label.", "df.loc[row_label, column_label]", "DataFrame and labels", "df = pd.DataFrame({'x': [2, 4]}, index=['a', 'b']); print(df.loc['b', 'x'])", "Prints 4", "Label slices include the ending label."),
        ("iloc", "Select rows and columns by integer position.", "df.iloc[row_position, column_position]", "DataFrame and integer positions", "df = pd.DataFrame({'x': [2, 4]}, index=['a', 'b']); print(df.iloc[1, 0])", "Prints 4", "Positional slices exclude the stop position."),
        ("Filtering", "Select rows satisfying a condition.", "df.loc[condition, columns]", "DataFrame and Boolean Series", "df = pd.DataFrame({'x': [1, 4, 7]}); print(df.loc[df['x'] > 3, 'x'].tolist())", "Prints [4, 7]", "Use parentheses with & and | for combined conditions."),
        ("Sorting rows", "Order rows by a column, such as ID.", "df.sort_values('column')", "DataFrame and column name", "df = pd.DataFrame({'ID': [3, 1, 2]}); print(df.sort_values('ID')['ID'].tolist())", "Prints [1, 2, 3]", "Assign the returned table if you want to keep the new order."),
        ("value_counts", "Count occurrences of each category.", "s.value_counts()", "Series", "s = pd.Series(['a', 'b', 'a']); print(s.value_counts().to_dict())", "Prints {'a': 2, 'b': 1}", "Missing values are excluded unless dropna=False."),
        ("unique / nunique", "List distinct values or count them.", "s.unique(); s.nunique()", "Series", "s = pd.Series([2, 2, 4]); print(s.unique().tolist(), s.nunique())", "Prints [2, 4] 2", "nunique excludes missing values by default."),
        ("isna / notna", "Identify missing or present values.", "s.isna(); s.notna()", "Series or DataFrame", "print(pd.Series([1, None]).isna().tolist())", "Prints [False, True]", "Empty text is not automatically missing."),
        ("fillna", "Replace missing values using a justified rule.", "s.fillna(value)", "Series with missing values", "print(pd.Series([1, None]).fillna(0).tolist())", "Prints [1.0, 0.0]", "Zero is not always a meaningful replacement."),
        ("dropna", "Remove rows or columns with missing values.", "df.dropna(subset=['column'])", "DataFrame", "df = pd.DataFrame({'x': [1, None]}); print(len(df.dropna()))", "Prints 1", "Default row dropping can remove useful data from unrelated columns."),
        ("duplicated", "Mark repeated rows or values.", "df.duplicated(subset=['column'])", "DataFrame", "print(pd.Series([1, 1, 2]).duplicated().tolist())", "Prints [False, True, False]", "The first occurrence is kept by default."),
        ("drop_duplicates", "Keep one record per chosen key.", "df.drop_duplicates(subset=['ID'])", "DataFrame with repeated keys", "df = pd.DataFrame({'ID': [1, 1, 2]}); print(df.drop_duplicates()['ID'].tolist())", "Prints [1, 2]", "Decide which columns define a true duplicate before dropping."),
        ("Rename", "Make column labels clear and consistent.", "df.rename(columns={'old': 'new'})", "DataFrame and name mapping", "df = pd.DataFrame({'a': [1]}); print(list(df.rename(columns={'a': 'score'}).columns))", "Prints ['score']", "Without assignment or inplace=True, the original names remain."),
        ("astype", "Convert a column to a chosen datatype.", "df['x'] = df['x'].astype(type)", "Values convertible to target type", "print(pd.Series(['1', '2']).astype(int).tolist())", "Prints [1, 2]", "Invalid text causes an error; inspect bad entries first."),
        ("Series map", "Replace values with a dictionary or element function.", "s.map(mapping_or_function)", "Series", "print(pd.Series(['y', 'n']).map({'y': 1, 'n': 0}).tolist())", "Prints [1, 0]", "Unmapped dictionary keys become missing values."),
        ("Apply", "Run a function on a Series value or DataFrame axis.", "s.apply(function); df.apply(function, axis=...)", "Series or DataFrame", "print(pd.Series([2, 3]).apply(lambda x: x*x).tolist())", "Prints [4, 9]", "Prefer a built-in vectorized operation when it expresses the same work."),
        ("Groupby", "Split rows into groups before summarizing.", "df.groupby('group')['value'].sum()", "Group and value columns", "df = pd.DataFrame({'g': ['a','a','b'], 'x': [1,2,4]}); print(df.groupby('g')['x'].sum().to_dict())", "Prints {'a': 3, 'b': 4}", "groupby alone creates a grouping object, not a summary."),
        ("Aggregation", "Calculate multiple summaries at once.", "s.agg(['min', 'max', 'mean'])", "Numeric Series", "print(pd.Series([2, 4]).agg(['min', 'max']).tolist())", "Prints [2, 4]", "Choose summaries meaningful for the datatype."),
        ("Merge", "Match rows using a shared key column.", "left.merge(right, on='ID', how='left')", "Two DataFrames with key columns", "a = pd.DataFrame({'ID':[1,2]}); b = pd.DataFrame({'ID':[1], 'x':[8]}); print(a.merge(b, on='ID').shape)", "Prints (1, 2); inner join keeps matching keys", "Duplicate keys on both sides can multiply rows."),
        ("Join", "Combine tables using their indexes by default.", "left.join(right)", "DataFrames with meaningful indexes", "a = pd.DataFrame({'x':[1]}); b = pd.DataFrame({'y':[2]}); print(a.join(b).shape)", "Prints (1, 2)", "join aligns index labels, not necessarily row positions."),
        ("Concat", "Append tables along rows or columns.", "pd.concat([a, b], ignore_index=True)", "DataFrames", "a = pd.DataFrame({'x':[1]}); b = pd.DataFrame({'x':[2]}); print(pd.concat([a,b], ignore_index=True)['x'].tolist())", "Prints [1, 2]", "axis=1 aligns indexes; it is not a key-based merge."),
        ("Correlation", "Measure a numeric linear relationship.", "df[['x', 'y']].corr()", "Numeric columns", "df = pd.DataFrame({'x':[1,2,3], 'y':[2,4,6]}); print(round(df.corr().loc['x','y'], 2))", "Prints 1.0", "Correlation does not prove causation; constant columns yield NaN."),
    ],
    "Data cleaning": [
        ("Detect missing values", "Count gaps before choosing how to handle them.", "df.isna().sum()", "Raw DataFrame", "df = pd.DataFrame({'x':[1,None]}); print(df.isna().sum().to_dict())", "Prints {'x': 1}", "Do not fill all columns with one value without checking meaning."),
        ("Check duplicates", "Inspect repeated keys before deleting records.", "df[df.duplicated('ID', keep=False)]", "Raw table and identity key", "df = pd.DataFrame({'ID':[1,1,2]}); print(df.duplicated('ID', keep=False).tolist())", "Prints [True, True, False]", "Repeated measurements may be legitimate, not duplicates."),
        ("Correct numeric types", "Find non-numeric text in numeric columns.", "pd.to_numeric(s, errors='coerce')", "Text Series", "s = pd.to_numeric(pd.Series(['2','bad']), errors='coerce'); print(s.isna().tolist())", "Prints [False, True]", "Coercion creates missing values; inspect them instead of hiding them."),
        ("Clean text / categories", "Remove accidental spaces and case differences.", "s.str.strip().str.lower()", "Text Series", "print(pd.Series([' Yes ', 'YES']).str.strip().str.lower().tolist())", "Prints ['yes', 'yes']", "Normalization may merge categories whose case is meaningful."),
        ("Inconsistent categories", "Map alternate spellings to one chosen label.", "s.replace(mapping)", "Text Series and verified mapping", "print(pd.Series(['M', 'male']).replace({'M':'male'}).tolist())", "Prints ['male', 'male']", "Keep the mapping explicit; do not guess ambiguous labels."),
        ("Outlier awareness", "Flag unusual values for investigation.", "q1=s.quantile(.25); q3=s.quantile(.75); iqr=q3-q1", "Numeric Series", "s = pd.Series([1,2,3,4,100]); q1=s.quantile(.25); q3=s.quantile(.75); print((s > q3+1.5*(q3-q1)).tolist())", "Prints [False, False, False, False, True]", "An outlier flag does not justify automatic deletion."),
        ("Validity filtering", "Select records that satisfy known domain rules.", "df.loc[df['age'].between(0, 120)]", "Table and justified bounds", "s = pd.Series([-1,20,130]); print(s.between(0,120).tolist())", "Prints [False, True, False]", "Keep an audit of removed rows; bounds depend on the problem."),
        ("Z-score standardization", "Express distance from the mean in standard-deviation units.", "z = (x - x.mean()) / x.std(ddof=0)", "Numeric array with nonzero standard deviation", "x = np.array([2.,4.,6.]); z = (x-x.mean())/x.std(ddof=0); print(z.round(3).tolist())", "Prints [-1.225, 0.0, 1.225]", "Choose population ddof=0 or sample ddof=1 deliberately; constant columns cannot be standardized this way."),
        ("Z-score outlier check", "Flag unusual distances for investigation, not automatic deletion.", "np.abs(z) > threshold", "Finite standardized scores and justified threshold", "z = np.array([-3.5,0.,2.,4.]); print((np.abs(z)>3).tolist())", "Prints [True, False, False, True]", "A threshold of 3 is a heuristic; skewed distributions need more care."),
        ("Check after cleaning", "Confirm shape, missingness and types after each step.", "clean.shape; clean.isna().sum(); clean.dtypes", "Original and cleaned DataFrames", "df = pd.DataFrame({'x':[1,None]}); clean = df.dropna(); print(len(df)-len(clean))", "Prints 1 removed row", "Always inspect what changed before overwriting your only copy."),
    ],
    "EDA": [
        ("Inspect the dataset", "Start EDA with size, types and missingness before summaries.", "df.shape; df.dtypes; df.isna().sum()", "Raw DataFrame", "df = pd.DataFrame({'score':[2, None, 6]}); print(df.shape, df['score'].isna().sum())", "Prints (3, 1) 1", "A mean alone hides missing observations and distribution."),
        ("Compare centre and spread", "Describe typical values and how dispersed they are.", "s.mean(); s.median(); s.std(ddof=1)", "Numeric Series", "s = pd.Series([2,4,6]); print(s.mean(), s.median(), s.std())", "Prints 4.0 4.0 2.0", "Pandas std uses sample ddof=1; NumPy defaults to population ddof=0."),
        ("Category proportions", "Compare relative frequencies when totals differ.", "s.value_counts(normalize=True, dropna=False)", "Categorical Series", "s = pd.Series(['A','A','B','B']); print(s.value_counts(normalize=True).to_dict())", "Prints {'A': 0.5, 'B': 0.5}", "State the denominator and whether missing values are included."),
        ("Compare groups", "Summarize group size and centre together.", "df.groupby('g')['x'].agg(['count', 'mean'])", "Group labels and numeric values", "df = pd.DataFrame({'g':['a','a','b'],'x':[2,4,8]}); print(df.groupby('g')['x'].mean().to_dict())", "Prints {'a': 3.0, 'b': 8.0}", "A small group's mean may be unstable; inspect its count and spread."),
    ],
    "Visualization": [
        ("Line plot", "Show change along an ordered axis such as time.", "plt.plot(x, y)", "Ordered x and numeric y", "plt.plot([1,2,3], [2,4,3]); plt.show()", "Displays a line through (1,2), (2,4), (3,3)", "Unsorted x values produce misleading connecting lines."),
        ("Bar plot", "Compare counts or values across categories.", "plt.bar(categories, values)", "Category labels and numeric heights", "plt.bar(['A','B'], [3,5]); plt.show()", "Displays bars of height 3 and 5", "A bar plot compares categories; a histogram bins numeric observations."),
        ("Scatter plot", "Inspect the relationship between two numeric variables.", "plt.scatter(x, y)", "Paired numeric values", "plt.scatter([1,2,3], [2,5,4]); plt.show()", "Displays three separate points", "A pattern in the dots does not establish causation."),
        ("Histogram", "Inspect the distribution of one numeric variable.", "plt.hist(values, bins=n)", "Numeric observations", "plt.hist([1,1,2,3], bins=[0.5,1.5,2.5,3.5]); plt.show()", "Displays three bins with counts 2, 1, 1", "Different bin choices change how the distribution looks."),
        ("Box plot", "Compare median, spread and potential outliers.", "plt.boxplot(values)", "Numeric observations", "plt.boxplot([1,2,3,4,100]); plt.show()", "Shows a box around the middle data and 100 as a flier", "Whiskers usually do not represent the minimum and maximum."),
        ("Labels / title / legend", "Explain axes, units and series meaning.", "plt.xlabel(...); plt.ylabel(...); plt.title(...); plt.legend()", "Plot plus meaningful labels", "plt.plot([1,2],[2,4], label='Score'); plt.xlabel('Week'); plt.ylabel('Marks'); plt.legend(); plt.show()", "Displays labelled axes and a Score legend", "legend needs labelled artists; avoid leaving units unexplained."),
        ("Figures / layout", "Keep plots separate and prevent clipped labels.", "plt.figure(); plt.tight_layout(); plt.show()", "Plot size and chart content", "plt.figure(figsize=(5,3)); plt.bar(['A','B'],[2,4]); plt.tight_layout(); plt.show()", "Displays a separate 5 by 3 inch figure", "Reuse an old figure accidentally and unrelated plots may overlap."),
    ],
}

OPERATION_CARDS = tuple(
    dict(zip(("what", "why", "syntax", "input", "example", "output", "mistake"), row),
         category=category, id=f"{category.lower().replace(' ', '-')}-{index}")
    for category, rows in _GROUPS.items()
    for index, row in enumerate(rows, 1)
)


# Derive executable expectations from the hand-authored display contract; never
# from executing the examples. Descriptive/graphical output has no exact string.
for _card in OPERATION_CARDS:
    _output = _card["output"]
    if _output.startswith("Prints ") and _card["what"] != "Info":
        _expected = _output[7:].split(";", 1)[0]
        _expected = {"0, 1, 2 on separate lines": "0\n1\n2", "2 then 1": "2\n1",
                     "1 removed row": "1"}.get(_expected, _expected)
        _card["expected_stdout"] = _expected


def recommend_cards(query, *, card_id="", limit=3):
    """Small deterministic catalogue lookup. Never reads assessment metadata."""
    import re
    words = {word for word in re.findall(r"[a-z_]+", query.lower()) if len(word) > 2}
    ranked = []
    for position, card in enumerate(OPERATION_CARDS):
        text = " ".join(card[key] for key in ("what", "why", "syntax", "mistake")).lower()
        score = sum(word in text for word in words)
        if card["id"] == card_id:
            score += 1000
        if score:
            ranked.append((-score, position, card))
    return [dict(card) for _, _, card in sorted(ranked)[:limit]]
