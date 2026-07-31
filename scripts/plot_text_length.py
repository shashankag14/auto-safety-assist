import json
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path


# path to recall and complaints data
DATA_DIR = Path('data')
recalls = json.loads((DATA_DIR / 'recalls.json').read_text())
complaints = json.loads((DATA_DIR / 'complaints.json').read_text())

recalls_df = pd.DataFrame(recalls)
complaints_df = pd.DataFrame(complaints)
print("Number of recalls:", len(recalls_df))
print("Number of complaints:", len(complaints_df))

# get word count from data
def word_count(series: pd.Series):
    return series.fillna('').str.split().str.len()

# get the text fields
fields = {
    'recall.Summary': word_count(recalls_df['Summary']),
    'recall.Consequence': word_count(recalls_df['Consequence']),
    'recall.Remedy': word_count(recalls_df['Remedy']),
    'complaint.summary': word_count(complaints_df['summary']),
}
print(pd.DataFrame({k: v.describe() for k, v in fields.items()}))

# plot historgrams
fig, axes = plt.subplots(2, 2, figsize=(12, 8))
for ax, (name, counts) in zip(axes.flat, fields.items()):
    ax.hist(counts, bins=30)
    ax.set_title(name)
fig.savefig(DATA_DIR / 'plots.png')