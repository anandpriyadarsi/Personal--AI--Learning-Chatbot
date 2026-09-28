"""Source-backed canonical topic catalogues for Anand's Semester-1 academic courses.

These names are stable assessment/RAG taxonomy labels. Do not rename a published
canonical topic casually: assessment packages and learning evidence refer to them.
Aliases may be expanded without changing canonical identities.

Source policy:
* MA103N, UC100N and CY100N use the supplied official NITK course plans.
* UC103N uses the supplied class-note set and the exact topic labels already used
  by the 90-question ANVAYA practice package, so current review handoffs map 1:1.
* DE100N has no detailed official course plan in the supplied evidence. Only the
  two concepts explicitly present in the confirmed course title are seeded; do
  not invent empathy/define/ideate/etc. until a course source is supplied.
"""

from __future__ import annotations

from typing import Mapping, Tuple


def _topic(name: str, *aliases: str) -> Mapping[str, object]:
    return {"name": name, "aliases": tuple(aliases)}


CATALOGUE_VERSION = 1

COURSE_CATALOGUE_METADATA = {
    "MA103N": {
        "course_name": "Linear Algebra",
        "source": "NITK MA103N Course Plan and Evaluation Plan (2026-27)",
        "coverage": "full_semester",
    },
    "UC100N": {
        "course_name": "Data Science and Artificial Intelligence",
        "source": "NITK UC100N Data Science & Artificial Intelligence Course Plan (2026-27)",
        "coverage": "full_semester",
    },
    "CY100N": {
        "course_name": "Engineering Chemistry",
        "source": "NITK CY100N Course Content and Evaluation Plan (2026-27)",
        "coverage": "full_semester_plus_lab",
    },
    "UC103N": {
        "course_name": "Indian Knowledge System",
        "source": "Supplied UC103N class-note set used by the 90-question practice package",
        "coverage": "supplied_material",
    },
    "DE100N": {
        "course_name": "Design Thinking and Prototyping",
        "source": "Confirmed course title only; detailed course plan not supplied",
        "coverage": "minimal_source_backed",
    },
}


MA103N_CANONICAL_TOPICS: Tuple[Mapping[str, object], ...] = (
    _topic("System of Linear Equations", "Systems of Linear Equations", "Linear Systems"),
    _topic("Elementary Row Operations", "Row Operations", "Elementary Row Operation"),
    _topic("Echelon Form", "Row Echelon Form", "REF"),
    _topic("RREF", "Reduced Row Echelon Form", "Reduced Echelon Form"),
    _topic("Rank of Matrix", "Matrix Rank", "Rank"),
    _topic("Rouche-Capelli Theorem", "Rouché-Capelli Theorem", "Rouché–Capelli Theorem", "Rouche Capelli Theorem"),
    _topic("Consistency of Linear Systems", "Consistency and Inconsistency", "Consistency/Inconsistency", "Consistency of Linear Equations"),
    _topic("Solution Classification", "Unique Infinite and No Solution", "Unique/Infinite/No Solution", "Unique Solution Infinite Solutions No Solution"),
    _topic("Gauss Elimination", "Gaussian Elimination"),
    _topic("Gauss-Jordan Method", "Gauss Jordan Method", "Gauss-Jordan Elimination"),
    _topic("Inverse using Gauss-Jordan", "Matrix Inverse using Gauss-Jordan", "Matrix Inverses using Elimination", "Inverse by Elimination", "Matrix Inverse"),
    _topic("LU Factorisation", "LU Factorization", "LU Decomposition", "LU-factorization"),
    _topic("Determinants", "Determinant"),
    _topic("Vector Spaces", "Vector Space"),
    _topic("Vector Space Axioms", "Axioms of Vector Spaces"),
    _topic("Vector Space Examples and Standard Spaces", "Standard Vector Spaces", "Examples of Vector Spaces"),
    _topic("Basic Structural Properties of Vector Spaces", "Structural Properties of Vector Spaces", "Basic Structural Properties"),
    _topic("Subspaces", "Subspace"),
    _topic("Linear Independence", "Linear Dependence and Independence", "Linear Independence Test"),
    _topic("Bases", "Basis"),
    _topic("Dimension", "Dimensions", "Dimension of a Vector Space"),
    _topic("Span", "Spanning Sets"),
    _topic("Basis Theorems", "Fundamental Results on Bases", "Basis Results"),
    _topic("Coordinate Representations", "Coordinate Representation", "Coordinates Relative to a Basis", "Bases and Coordinate Representations"),
    _topic("Dimension Theorems", "Dimension-related Theorems", "Dimension Related Theorems"),
    _topic("Inner Products in R^n", "Inner Product in R^n", "Inner Products"),
    _topic("Orthogonal and Orthonormal Sets", "Orthogonal Sets", "Orthonormal Sets"),
    _topic("Orthogonal Matrices", "Orthogonal Matrix"),
    _topic("Gram-Schmidt Process", "Gram Schmidt", "Gram-Schmidt", "Gram-Schmidt Orthonormalization"),
    _topic("Orthonormal Bases", "Orthonormal Basis"),
    _topic("Orthogonal Complements", "Orthogonal Complement"),
    _topic("QR Factorisation", "QR Factorization", "QR Decomposition"),
    _topic("Least Squares", "Least Squares Problems", "Least-squares"),
    _topic("Best Approximation", "Best Approximation Problems", "Best Approximation Theorem"),
    _topic("Linear Transformations", "Linear Transformation"),
    _topic("Range of a Linear Transformation", "Range", "Image of a Linear Transformation"),
    _topic("Null Space", "Kernel", "Nullspace"),
    _topic("Invertibility of Linear Transformations", "Invertible Linear Transformations", "Invertibility"),
    _topic("Rank-Nullity Theorem", "Rank Nullity Theorem"),
    _topic("Matrix Representation of Linear Transformations", "Matrix Representations", "Matrix Representation"),
    _topic("Change of Basis", "Change of Basis Matrix"),
    _topic("Similarity", "Similar Matrices", "Similarity Concepts"),
    _topic("Eigenvalues", "Eigenvalue"),
    _topic("Eigenvectors", "Eigenvector"),
    _topic("Characteristic Polynomial", "Characteristic Polynomials", "Characteristic Equation"),
    _topic("Cayley-Hamilton Theorem", "Cayley Hamilton Theorem"),
    _topic("Diagonalization", "Diagonalisation", "Matrix Diagonalization"),
    _topic("Positive Semidefinite Matrices", "Positive Semidefinite Matrix", "PSD Matrices"),
    _topic("Quadratic Forms", "Quadratic Form"),
    _topic("Spectral Theorem"),
    _topic("Singular Value Decomposition", "SVD"),
)


UC100N_CANONICAL_TOPICS: Tuple[Mapping[str, object], ...] = (
    _topic("Introduction to Data Science and AI", "Introduction to Data Science & AI"),
    _topic("Applications of Data Science", "Applications of Data Science in Engineering and Society"),
    _topic("Types of Data", "Data Types"),
    _topic("Basics of Vectors and Matrices", "Basics of Vector and Matrix"),
    _topic("Python Environment", "Introduction to Python Environment"),
    _topic("Python Basic Commands", "Basic Python Commands"),
    _topic("Python Arithmetic Operations", "Arithmetic Operations in Python"),
    _topic("Vector and Matrix Creation", "Creating Vectors and Matrices"),
    _topic("Data Science Workflow", "Data Science Pipeline"),
    _topic("Data Representation"),
    _topic("Matrix Representation and Operations", "Matrix Representation", "Matrix Operations"),
    _topic("Matrix Addition"),
    _topic("Matrix Multiplication"),
    _topic("Matrix Transpose", "Transpose"),
    _topic("Dot Products", "Dot Product"),
    _topic("Real World Datasets", "Real World Dataset"),
    _topic("Descriptive Statistics", "Descriptive Statistics for Data Analysis"),
    _topic("Mean"),
    _topic("Median"),
    _topic("Mode"),
    _topic("Variance"),
    _topic("Standard Deviation"),
    _topic("Range"),
    _topic("Interquartile Range", "IQR"),
    _topic("Data Import", "CSV and Excel Data Import", "Import CSV/Excel Files"),
    _topic("Statistical Analysis"),
    _topic("Data Cleaning"),
    _topic("Missing Data", "Missing Values", "Handling Missing Data"),
    _topic("Inconsistent Data", "Handling Inconsistent Data"),
    _topic("Removing Duplicates", "Duplicate Removal"),
    _topic("Handling Outliers", "Outliers"),
    _topic("Data Normalization", "Normalization"),
    _topic("Data Encoding", "Encoding"),
    _topic("Data Reduction", "Feature Reduction"),
    _topic("Feature Selection"),
    _topic("Data Transformation", "Transformation"),
    _topic("Introduction to Machine Learning", "Machine Learning Introduction"),
    _topic("Supervised Learning"),
    _topic("Regression"),
    _topic("Classification"),
    _topic("Data Visualization", "Data Visualizations"),
    _topic("Bar Charts", "Bar Chart"),
    _topic("Line Graphs", "Line Graph"),
    _topic("Histograms", "Histogram"),
    _topic("Scatterplots", "Scatter Plots", "Scatterplot"),
    _topic("Visualization Labels, Titles and Legends", "Labelling Axes Titles and Legends"),
    _topic("Unsupervised Learning"),
    _topic("Clustering"),
    _topic("Dimensionality Reduction"),
    _topic("Model Evaluation", "Evaluation Metrics and Significance"),
    _topic("Overfitting", "Over Fitting"),
    _topic("Underfitting", "Under Fitting"),
    _topic("Good Fit Models", "Good-fit Models"),
    _topic("Neural Networks", "Basics of Neural Network"),
    _topic("Deep Learning", "Basics of Deep Learning"),
    _topic("AI Use Cases and Applications", "AI Use Cases", "AI Applications"),
    _topic("AI Tools", "ChatGPT Gemini Copilot Claude DALL-E NotebookLM"),
    _topic("Text Summarization", "Text Summarisation"),
    _topic("Text Generation"),
    _topic("AI Ethics and Societal Implications", "AI Ethics"),
    _topic("Privacy in AI", "Privacy"),
    _topic("Responsible Use of AI", "Responsible AI Use"),
    _topic("AI-Assisted Code Generation", "Code Generation"),
    _topic("AI-Assisted Image Generation", "Image Generation"),
    _topic("Course Project - Data Analysis", "Course Project Data Analysis"),
    _topic("Course Project - ML Modelling", "Course Project ML Modelling", "ML Modeling"),
    _topic("Course Project - Model Evaluation", "Course Project Model Evaluation"),
)


CY100N_CANONICAL_TOPICS: Tuple[Mapping[str, object], ...] = (
    _topic("Introduction to Spectroscopy", "Spectroscopy"),
    _topic("Electromagnetic Spectrum and Energy", "Electromagnetic Spectrum"),
    _topic("Absorption and Emission Spectra", "Absorption Spectra", "Emission Spectra"),
    _topic("UV-Vis Spectroscopy", "UV-Visible Spectroscopy", "UV Vis Spectroscopy"),
    _topic("Chromophore and Auxochrome", "Chromophores and Auxochromes"),
    _topic("Beer-Lambert Law", "Beer Lambert Law", "Beer–Lambert Law"),
    _topic("Fluorescence and Phosphorescence", "Fluorescence", "Phosphorescence"),
    _topic("Infra-Red Spectroscopy", "Infrared Spectroscopy", "IR Spectroscopy"),
    _topic("Modes of Vibrations", "Vibrational Modes"),
    _topic("Vibration Frequency of Chemical Bonds", "Bond Vibration Frequencies"),
    _topic("Characteristic Vibration Frequencies", "Characteristic Bond Frequencies"),
    _topic("Microscopic Techniques", "Introduction to Microscopic Techniques"),
    _topic("Atomic Absorption Spectroscopy", "AAS"),
    _topic("Single Electrode Potential", "Electrode Potential"),
    _topic("Electrochemical Series"),
    _topic("Calomel Electrode"),
    _topic("Glass Electrode"),
    _topic("Polarization", "Polarisation"),
    _topic("Decomposition Potential"),
    _topic("Overvoltage", "Over Voltage"),
    _topic("Lead-Storage Batteries", "Lead Storage Battery", "Lead Acid Battery"),
    _topic("Fuel Cells", "Introduction to Fuel Cells"),
    _topic("Electroplating Theory", "Electroplating"),
    _topic("Factors Affecting Electrodeposit", "Factors Affecting the Nature of Deposit"),
    _topic("Electroplating of Copper", "Copper Electroplating"),
    _topic("Multilayer Coating", "Multilayer Coating and Applications"),
    _topic("Electroless Plating of Copper", "Electroless Copper Plating"),
    _topic("PCB Preparation", "Printed Circuit Board Preparation"),
    _topic("Electrochemical Corrosion", "Theory of Electrochemical Corrosion"),
    _topic("Factors Affecting Corrosion Rate", "Corrosion Rate Factors"),
    _topic("General Corrosion"),
    _topic("Galvanic Corrosion", "Galvanic Series"),
    _topic("Differential Aeration Corrosion", "Differential Aeration"),
    _topic("Pitting Corrosion", "Pitting"),
    _topic("Stress Corrosion", "Stress Corrosion Cracking"),
    _topic("Cathodic Protection"),
    _topic("Anodic Protection"),
    _topic("Introduction to Nanomaterials", "Nanomaterials"),
    _topic("Nanomaterials vs Bulk Materials", "Comparison with Bulk Materials"),
    _topic("Size Effects in Nanomaterials", "Size Effects"),
    _topic("Chemical Vapour Deposition", "CVD", "Chemical Vapor Deposition"),
    _topic("Pulsed Laser Deposition", "PLD"),
    _topic("Sol-Gel Method", "Sol Gel"),
    _topic("Hydrothermal Method", "Hydrothermal Synthesis"),
    _topic("Nanocarbon", "Nanocarbon Types Preparation Properties and Applications"),
    _topic("ZnO Nanostructures", "ZnO Nanomaterials"),
    _topic("TiO2 Nanostructures", "TiO2 Nanomaterials"),
    _topic("Introduction to Green Chemistry", "Green Chemistry"),
    _topic("12 Principles of Green Chemistry", "Twelve Principles of Green Chemistry"),
    _topic("Atom Economy", "Atom Economy Calculation"),
    _topic("E-Factor", "E Factor"),
    _topic("Basic Polymer Definitions", "Polymer Definitions"),
    _topic("Polymer Classification by Mechanism", "Classification of Polymers by Mechanism"),
    _topic("Polymer Classification by Thermal Properties", "Classification of Polymers by Thermal Properties"),
    _topic("Polymer Tacticity", "Tacticity"),
    _topic("Copolymerization", "Copolymerisation"),
    _topic("Alternate Copolymers", "Alternating Copolymers"),
    _topic("Random Copolymers"),
    _topic("Block Copolymers"),
    _topic("Graft Copolymers"),
    _topic("Free Radical Polymerization", "Free Radical Polymerisation"),
    _topic("Cationic Polymerization", "Cationic Polymerisation"),
    _topic("Anionic Polymerization", "Anionic Polymerisation"),
    _topic("Coordination Polymerization", "Coordination Polymerisation"),
    _topic("Condensation Polymerization", "Condensation Polymerisation"),
    _topic("Number Average Molecular Weight", "Number-average Molecular Weight"),
    _topic("Weight Average Molecular Weight", "Weight-average Molecular Weight"),
    _topic("Bulk Polymerization", "Bulk Polymerisation"),
    _topic("Solution Polymerization", "Solution Polymerisation"),
    _topic("Suspension Polymerization", "Suspension Polymerisation"),
    _topic("Emulsion Polymerization", "Emulsion Polymerisation"),
    _topic("Glass Transition Temperature", "Tg"),
    _topic("Factors Affecting Glass Transition Temperature", "Factors Affecting Tg"),
    _topic("Polymer Structure-Property Relationships", "Effect of Polymer Structure on Properties"),
    _topic("Conducting Polymers", "Conductive Polymers"),
    _topic("Complexometric Titration with EDTA", "Total Hardness of Water by EDTA"),
    _topic("Redox Titration of Pyrolusite", "Manganese Dioxide in Pyrolusite"),
    _topic("Acid-Base Titration of Ammonium Fertilizer", "Nitrogen in Ammonium Fertilizer"),
    _topic("Conductometric Titration", "Strong Acid-Strong Base Conductometric Titration"),
    _topic("Colorimetric Estimation of Copper", "Colorimetry of Cu(II)", "Copper Colorimetry"),
    _topic("Green Organic Synthesis", "Green Synthesis"),
    _topic("Mechanochemistry", "Mechanochemical Synthesis"),
    _topic("Bio-Renewable Catalysts", "Biorenewable Catalyst"),
)


# These exact canonical names intentionally mirror the topic labels already used
# in UC103N.iks.90q.practice-test.001. That makes the current 90-question handoff
# deterministic once this catalogue is reconciled into ANVAYA.
UC103N_CANONICAL_TOPICS: Tuple[Mapping[str, object], ...] = (
    _topic("Introduction to the Vedas", "Introduction to Vedas"),
    _topic("Genesis of Vedic literature", "Genesis of Vedic Literature"),
    _topic("Oral transmission", "Shruti", "Oral Tradition"),
    _topic("Organisation of Vedic knowledge", "Organization of Vedic Knowledge"),
    _topic("Four divisions of each Veda", "Four Divisions of the Vedas"),
    _topic("Saṃhitā", "Samhita"),
    _topic("Brāhmaṇa", "Brahmana"),
    _topic("Āraṇyaka", "Aranyaka"),
    _topic("Upaniṣad", "Upanishad", "Upanishads"),
    _topic("Rigveda", "Rig Veda"),
    _topic("Yajurveda", "Yajur Veda"),
    _topic("Sāmaveda", "Sama Veda", "Samaveda"),
    _topic("Atharvaveda", "Atharva Veda"),
    _topic("Notable Rigvedic hymns", "Rigvedic Hymns"),
    _topic("Notable Atharvavedic hymns", "Atharvavedic Hymns"),
    _topic("Upavedas", "Upaveda"),
    _topic("Vedāṅgas", "Vedangas", "Vedanga"),
    _topic("Vedāṅgas - Chandas", "Chandas", "Chandah"),
    _topic("Classification of darśanas", "Classification of Darshanas", "Darshana Classification"),
    _topic("Āstika and nāstika", "Astika and Nastika"),
    _topic("Goal of philosophy", "Goal of Indian Philosophy"),
    _topic("Sāṃkhya", "Samkhya", "Sankhya"),
    _topic("Sāṃkhya liberation", "Samkhya Liberation", "Kaivalya in Samkhya"),
    _topic("Puruṣa and Prakṛti", "Purusha and Prakriti"),
    _topic("Pramāṇas", "Pramanas", "Sources of Valid Knowledge"),
    _topic("Eight limbs of Yoga", "Ashtanga Yoga", "Eight Limbs of Yoga"),
    _topic("Five states of mind", "Five States of Mind"),
    _topic("Nyāya and Vaiśeṣika", "Nyaya and Vaisheshika"),
    _topic("Nyāya bondage", "Nyaya Bondage"),
    _topic("Vaiśeṣika system", "Vaisheshika System"),
    _topic("Vaiśeṣika atomic theory", "Vaisheshika Atomic Theory"),
    _topic("Pūrva Mīmāṃsā", "Purva Mimamsa", "Mimamsa"),
    _topic("Vedānta", "Vedanta", "Uttara Mimamsa"),
    _topic("Pāṇini background", "Panini Background"),
    _topic("Aṣṭādhyāyī", "Ashtadhyayi"),
    _topic("Trimuni Vyākaraṇa", "Trimuni Vyakarana"),
    _topic("Śiva-sūtras", "Shiva Sutras", "Siva Sutras"),
    _topic("Qualities of sūtras", "Qualities of Sutras", "Sutra Qualities"),
    _topic("Sanskrit vocabulary"),
    _topic("Word formation"),
    _topic("Word generation"),
    _topic("Phonetics", "Sanskrit Phonetics"),
    _topic("Pāṇini's contributions", "Panini's Contributions", "Panini Contributions"),
    _topic("Sanskrit and NLP", "Sanskrit for NLP", "Sanskrit and Natural Language Processing"),
    _topic("Why Sanskrit for NLP"),
    _topic("Handling ambiguity", "Ambiguity Handling"),
    _topic("Key linguistic principles", "Linguistic Principles"),
    _topic("Text and context", "Text and Context"),
    _topic("Bhāskarācārya's life", "Bhaskaracharya's Life", "Bhaskaracharya"),
    _topic("About Lilāvatī", "About Lilavati", "Lilavati"),
    _topic("Methods of finding squares", "Finding Squares"),
    _topic("Worked square example", "Square Example"),
    _topic("Squaring identity", "Square Identity"),
    _topic("Square-root extraction", "Square Root Extraction"),
    _topic("Methods of finding cubes", "Finding Cubes"),
    _topic("Cube-root extraction", "Cube Root Extraction"),
    _topic("Fractions"),
    _topic("Completing the square", "Completing Square"),
    _topic("Difference of squares", "Difference of Squares"),
    _topic("Combinations", "Combination"),
    _topic("Permutations", "Permutation"),
    _topic("Permutations with repetition", "Permutations with Repetition"),
    _topic("Progressions", "Progression"),
    _topic("Mensuration - right triangles", "Mensuration - Right Triangles", "Right Triangle Mensuration"),
    _topic("Mensuration - quadrilaterals", "Mensuration - Quadrilaterals", "Quadrilateral Mensuration"),
    _topic("Mensuration - circle", "Mensuration - Circle", "Circle Mensuration"),
    _topic("Shared concepts", "Shared Concepts"),
    _topic("Origins", "Origins of Hinduism Buddhism and Jainism"),
    _topic("Jain theology", "Jain Theology"),
    _topic("Buddhist metaphysics", "Buddhist Metaphysics"),
    _topic("Jain metaphysics", "Jain Metaphysics"),
    _topic("Advaita Vedānta", "Advaita Vedanta", "Advaita"),
    _topic("Viśiṣṭādvaita", "Vishishtadvaita", "Qualified Non-Dualism"),
    _topic("Dvaita", "Dvaita Vedanta", "Dualism"),
    _topic("Mahāvākyas", "Mahavakyas"),
    _topic("Buddhist schools", "Buddhist Schools"),
    _topic("Four Noble Truths"),
    _topic("Three Marks of Existence"),
    _topic("Buddhist path", "Buddhist Path", "Eightfold Path"),
    _topic("Jain path", "Jain Path", "Three Jewels"),
    _topic("Jain Tīrthaṅkaras", "Jain Tirthankaras", "Tirthankaras"),
)


DE100N_CANONICAL_TOPICS: Tuple[Mapping[str, object], ...] = (
    _topic("Design Thinking", "Design-Thinking"),
    _topic("Prototyping", "Prototype Development"),
)


CANONICAL_TOPIC_CATALOGUES = {
    "MA103N": MA103N_CANONICAL_TOPICS,
    "UC100N": UC100N_CANONICAL_TOPICS,
    "CY100N": CY100N_CANONICAL_TOPICS,
    "UC103N": UC103N_CANONICAL_TOPICS,
    "DE100N": DE100N_CANONICAL_TOPICS,
}


def catalogue_for(course_code: str) -> Tuple[Mapping[str, object], ...]:
    return tuple(CANONICAL_TOPIC_CATALOGUES.get(str(course_code).strip().upper(), ()))


def canonical_names(course_code: str) -> Tuple[str, ...]:
    return tuple(str(item["name"]) for item in catalogue_for(course_code))


def aliases_for(course_code: str, canonical_name: str) -> Tuple[str, ...]:
    wanted = str(canonical_name).strip().casefold()
    for item in catalogue_for(course_code):
        if str(item["name"]).strip().casefold() == wanted:
            return tuple(str(alias) for alias in item.get("aliases", ()))
    return ()


__all__ = (
    "CATALOGUE_VERSION",
    "CANONICAL_TOPIC_CATALOGUES",
    "COURSE_CATALOGUE_METADATA",
    "MA103N_CANONICAL_TOPICS",
    "UC100N_CANONICAL_TOPICS",
    "CY100N_CANONICAL_TOPICS",
    "UC103N_CANONICAL_TOPICS",
    "DE100N_CANONICAL_TOPICS",
    "aliases_for",
    "canonical_names",
    "catalogue_for",
)
