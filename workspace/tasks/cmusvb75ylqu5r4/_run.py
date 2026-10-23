import pandas as pd
file_path = 'observations.xlsx'
data = pd.read_excel(file_path)
most_serious_observation = data.loc[data['Limit'].apply(lambda x: str(x).lower() != 'nan')].iloc[0]['Observation']
print(most_serious_observation)