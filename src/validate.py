import pandas as pd
import sys

sys.stdout = open("../in-out_files/errors.txt", "w", encoding="utf=8")

# Названия столбцов (заполните нужными значениями)
id_column = 'id'  # столбец с ID для группировки
df = pd.read_csv("../in-out_files/out.csv", delimiter=';', encoding='windows-1251')

grouped = df.groupby(id_column)

all_eq = ['Species', 'Sex']
cnt = 0
for group_id, group_data in grouped:
    # Вид
    unique_values = group_data['Species'].unique()
    if len(unique_values) != 1:
        cnt += 1
        print(
            f"{cnt}. У птицы с id {group_data[id_column].unique()[0]} не совпадает вид: имеются значения {unique_values.tolist()}")

    # Пол
    unique_values = group_data['Sex'].unique()
    # if 1 in unique_values and 2 in unique_values:
    if len(unique_values) != 1:
        cnt += 1
        print(
            f"{cnt}. У птицы с id {group_data[id_column].unique()[0]} не совпадает пол: имеются значения {unique_values.tolist()}")

    # Возраст
    unique_values = group_data['Age'].tolist()
    if any(unique_values[i] > unique_values[i + 1] for i in range(len(unique_values) - 1)):
        cnt += 1
        print(f"{cnt}. У птицы с id {group_data[id_column].unique()[0]} уменьшается возраст: имеются значения {unique_values}")
