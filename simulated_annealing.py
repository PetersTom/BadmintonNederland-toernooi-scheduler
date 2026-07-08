import pandas as pd
import itertools
from collections import defaultdict
import random
import math

def parse_csv(players_csv, matches_csv):
    df = pd.read_csv(players_csv, skiprows=3)

    # concattenate names
    df["full name"] = (
        (df["Voornaam"].fillna("").astype(str) + " " + df["Tussenvoegsel"].fillna("").astype(str) + " " + df["Naam"].fillna("").astype(str))
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )

    df["Naam"] = df["full name"]
    players = df[["Nr.", "Naam", "Onderdelen"]]

    df = pd.read_csv(matches_csv, skiprows=3)
    matches = df[["ID", "Nr", "Onderdeel", "Ronde", "Team 1", "Team 2"]]
    # Split the Onderdeel in the actual Onderdeel and a Groep field
    matches["Groep"] = matches["Onderdeel"].str.split(" - ").str[1].fillna("N/A")
    matches["Onderdeel"] = matches["Onderdeel"].str.split(" - ").str[0]
    # Rename field with spaces such that itertuples creates named tuples properly
    matches = matches.rename(columns={
        "Team 1": "Team_1",
        "Team 2": "Team_2"
    })
    matches["Nr"] = matches["Nr"].astype(int)
    matches, players = add_player_matches_to_dataframes(matches, players)
    matches = add_prior_matches_to_dataframes(matches)
    matches = add_prior_rondes_to_dataframes(matches)
    return players, matches


def get_match_parents_ID(matches, match_id):
    match = matches.loc[matches["ID"] == match_id].iloc[0]
    if match.Groep != "N/A":
        # we are in a groep phase and hence have no prerequisites
        return []
    amount_of_matches_in_onderdeel = matches.loc[matches["Onderdeel"] == match.Onderdeel]["Nr"].max() + 1  # the +1 is necessary because we want to index rounding from 1
    nr_inverted = amount_of_matches_in_onderdeel - match.Nr
    parent_nrs_inverted = [nr_inverted * 2, nr_inverted * 2 + 1]
    parent_nrs = [amount_of_matches_in_onderdeel - parent_nrs_inverted[0], amount_of_matches_in_onderdeel - parent_nrs_inverted[1]]
    parent_ids = matches.loc[(matches["Onderdeel"] == match.Onderdeel) & (matches["Nr"].isin(parent_nrs)), "ID"]
    parent_ids = parent_ids.tolist()

    # if we rely on a group phase, we add all group matches as a parent
    if not parent_ids:
        # we need to check if there is a group phase before this
        if "Groep" in match.Team_1:
            group_name = match.Team_1.split("#")[0].strip()
            parents = matches.loc[(matches["Onderdeel"] == match.Onderdeel) & (matches["Groep"] == group_name), "ID"]
            parent_ids.extend(parents.tolist())
        if "Groep" in match.Team_2:
            group_name = match.Team_2.split("#")[0].strip()
            parents = matches.loc[(matches["Onderdeel"] == match.Onderdeel) & (matches["Groep"] == group_name), "ID"]
            parent_ids.extend(parents.tolist())
    return parent_ids


def add_player_matches_to_dataframes(matches, players):
    can_play_in = defaultdict(set)
    matches = matches.sort_values(by="Groep", key=lambda col: col != "N/A")  # make sure to process groups first, before knockout
    for (onderdeel, _), onderdeel_df in matches.groupby(["Onderdeel", "Groep"]):
        onderdeel_df = onderdeel_df.sort_values(by="Nr")
        for match in onderdeel_df.itertuples(index=False):
            for index_in_player_matches, team in enumerate([match.Team_1, match.Team_2]):
                if "Winnaar" not in team and "#" not in team and "of" not in team:
                    # hopefully this just contains a name or two names separated by a +
                    if "+" in team:
                        team.split("+")
                        for player in team.split("+"):
                            can_play_in[match.ID].add(player.strip())
                    else:
                        can_play_in[match.ID].add(team.strip())
                elif "Groep" in team:
                    # todo fetch all the people in that group
                    group_name = team.split("#")[0].strip()
                    ids_of_group_matches = matches.loc[matches["Groep"] == group_name, "ID"].tolist()
                    for id in ids_of_group_matches:
                        can_play_in[match.ID].update(can_play_in[id])
                    pass
                else:
                    parent_ids = get_match_parents_ID(matches, match.ID)
                    parent_id = parent_ids[index_in_player_matches]  # the specific parent of this team
                    can_play_in[match.ID].update(can_play_in[parent_id])

    total_players = set(players["Naam"])
    for players_in_match in can_play_in.values():
        assert players_in_match.issubset(total_players)

    matches["Players"] = matches["ID"].map(can_play_in)
    
    exploded_matches = matches.explode("Players")
    inverted = exploded_matches.groupby("Players")["ID"].apply(set).reset_index()
    inverted = inverted.rename(columns={"Players": "Naam"})
    players = players.merge(inverted, on="Naam", how="left")
    players = players.rename(columns={"ID": "Match_ID"})
    return matches, players


def add_prior_matches_to_dataframes(matches):
    prerequisites = defaultdict(list)
    for match in matches.itertuples():
        to_process = [match.ID]
        while to_process:
            x = to_process.pop(0)
            parents = get_match_parents_ID(matches, x)
            prerequisites[match.ID].extend(parents)
            to_process.extend(parents)
    matches["Prerequisites"] = matches["ID"].map(prerequisites)
    return matches

def add_prior_rondes_to_dataframes(matches):
    new_column_prerequisite_rondes = {}
    onderdeel_rondes = list(matches[['Onderdeel', 'Ronde']].drop_duplicates().itertuples(index=False, name=None))
    for onderdeel, ronde in onderdeel_rondes:
        relevant_matches = matches.loc[(matches['Onderdeel'] == onderdeel) & (matches['Ronde'] == ronde), 'Prerequisites']
        prerequisite_matches_ids = sum(relevant_matches, [])
        prerequisite_matches = matches.loc[matches['ID'].isin(prerequisite_matches_ids), ['Onderdeel', 'Ronde']]
        prerequisite_rondes = [onderdeel + " " + ronde for onderdeel, ronde in prerequisite_matches.drop_duplicates().itertuples(index=False, name=None)]
        new_column_prerequisite_rondes[(onderdeel, ronde)] = prerequisite_rondes
    
    matches["Prerequisite_Rondes"] = matches[['Onderdeel', 'Ronde']].apply(tuple, axis=1).map(new_column_prerequisite_rondes)
    return matches


"""
Returns true if a solution is valid. It checks the following things:
- Matches are played before their children
- A player cannot possibly play two matches in the same round
- There are not too many matches per round
- Each match is only played once
"""
def is_valid(solution, players, matches, matches_per_round, output=True):
    # check order
    parsed = []
    for r in solution:
        for match_id in r:
            requirements = get_match_parents_ID(matches, match_id)
            if any(req not in parsed for req in requirements):
                if output:
                    print(matches)
                    print(f"{match_id} is before one of it's requirements {requirements}")
                    print(solution)
                return False
        parsed.extend(r)

    # check no two matches in the same round
    def no_two_same_round_rec(index_in_player_matches, used_rounds, player_matches, solution):
        if index_in_player_matches == len(player_matches):
            return True
        
        y = player_matches[index_in_player_matches]
        for j, sublist in enumerate(solution):
            if j not in used_rounds and y in sublist:
                if no_two_same_round_rec(index_in_player_matches + 1, used_rounds | {j}, player_matches, solution):
                    return True
        return False

    for player in players.itertuples():
        if not no_two_same_round_rec(0, set(), list(player.Match_ID), solution):
            if output:
                print(matches)
                print(f"player might play two matches at the same time or not all of their matches are played:")
                print(player.Match_ID)
                print(solution)
            return False

    # not too many matches per round
    if any(len(r) > matches_per_round for r in solution):
        if output:
            print("Too many matches in one of the rounds")
            print(solution)
        return False

    # each match only played once
    if len([x for y in solution for x in y]) != len(matches):
        if output:
            print("# matches scheduled doesn't match total # of matches.")
        return False


    return True
    

def valid_swap(a, b, players, matches):
    match_a_prerequisites = matches.loc[matches["ID"] == a, "Prerequisites"].iloc[0]
    match_b_prerequisites = matches.loc[matches["ID"] == b, "Prerequisites"].iloc[0]

    if b in match_a_prerequisites or a in match_b_prerequisites:
        return False
    
    for matches_of_one_player in players["Match_ID"]:
        if a in matches_of_one_player and b in matches_of_one_player:
            return False
    return True



def exhaustive_swap_random_valid_match(solution, players, matches):
    all_valid_swaps = []
    for r1, r2 in itertools.combinations(range(len(solution)), 2):
        # find all valid swaps in these rounds
        potential_swaps = list(itertools.product(solution[r1], solution[r2]))
        potential_swaps = [(r1, r2, a, b) for (a, b) in potential_swaps if valid_swap(a, b, players, matches)]
        all_valid_swaps.extend(potential_swaps)
    (r1, r2, a, b) = random.choice(all_valid_swaps)
    new_solution = [r[:] for r in solution]
    new_solution[r1].remove(a)
    new_solution[r2].remove(b)
    new_solution[r1].append(b)
    new_solution[r2].append(a)
    return new_solution

def swap_random_valid_match(solution, players, matches, matches_per_round):
    while True:
        r1, r2 = random.sample(range(len(solution)), 2)
        solution[r1].append(None)
        solution[r2].append(None)
        a = random.choice(solution[r1])
        b = random.choice(solution[r2])
        new_solution = [r[:] for r in solution]
        new_solution[r1].remove(a)
        new_solution[r2].remove(b)
        new_solution[r1].append(b)
        new_solution[r2].append(a)
        while None in new_solution[r1]:
            new_solution[r1].remove(None)
        while None in new_solution[r2]:
            new_solution[r2].remove(None)
        while None in solution[r1]:
            solution[r1].remove(None)
        while None in solution[r2]:
            solution[r2].remove(None)
        if is_valid(new_solution, players, matches, matches_per_round, False):
            return  new_solution


def swap_random_valid_ronde(solution, players, matches, matches_per_ronde):
    while True:
        r1, r2 = random.sample(range(len(solution)), 2)
        onderdeel1, ronde1 = solution[r1].split(" ")
        onderdeel2, ronde2 = solution[r2].split(" ")
        r1_prerequisites = list(matches.loc[(matches['Onderdeel'] == onderdeel1) & (matches['Ronde'] == ronde1), "Prerequisite_Rondes"].iloc[0])
        r2_prerequisites = list(matches.loc[(matches['Onderdeel'] == onderdeel2) & (matches['Ronde'] == ronde2), "Prerequisite_Rondes"].iloc[0])
        # todo: check if this is a valid swap. For this, we need to copy the solution and check the full solution using the prerequisite Rondes

        




"""
A solution is a list of "rondes". This is easy to schedule in the toernooi planner. However, to calculate a proper cost, we first need to actually convert it and schedule each match greedily
We assume here that the solution is valid, i.e. no match will be played after a match that requires it. Hence, we only need to ensure a player doesn't play multiple matches in a round
"""
def ronde_cost(solution, players, matches, matches_per_round):
    match_schedule = [[]]
    non_full_round = 0
    for onderdeel_ronde in solution:
        # schedule the matches in this ronde greedily
        onderdeel, ronde = onderdeel_ronde.split(" ")
        matches_to_schedule = matches.loc[(matches['Onderdeel'] == onderdeel) & (matches['Ronde'] == ronde)]
        for match in matches_to_schedule.itertuples():
            # schedule match in first available round
            round_to_check = non_full_round
            while True: # not scheduled
                # if the round we want to check is too high, extend the list to include an empty round for that round index
                if round_to_check >= len(match_schedule):
                    match_schedule.extend([[] for _ in range(round_to_check + 1 - len(match_schedule))])

                # if the round is already full, continue to the next one
                # if this was the first non-full round, also increase that counter
                if len(match_schedule[round_to_check]) == matches_per_round:
                    if round_to_check == non_full_round:
                        non_full_round += 1
                    round_to_check += 1
                    continue

                matches_already_in_round = match_schedule[round_to_check]
                players_already_in_round = set().union(*matches.loc[matches['ID'].isin(matches_already_in_round), "Players"])
                if not bool(set(players_already_in_round) & set(match.Players)):
                    # schedule and continue to next match
                    match_schedule[round_to_check].append(match.ID)
                    break
                else:
                    # doesn't fit in this round, increase round and try again
                    round_to_check += 1
    return match_cost(match_schedule, players, matches, matches_per_round)



"""
A solution is a list of lists. Each list contains the IDs of the matches in that round.
rules:
Finals as late as possible
Matches played as early as possible + no empty spots early
Match spread
"""
def match_cost(solution, players, matches, matches_per_round):
    final_ids = matches.loc[matches["Ronde"] == "Finale", "ID"]
    matches_after_first_final = 0
    first_final_round = 0
    for i, r in enumerate(solution):
        if any(match_id in final_ids for match_id in r):
            first_final_round = i
            break
    not_final_matches_after_first_final = [match_id for r in solution[first_final_round + 1:] for match_id in r if match_id not in final_ids.tolist()]
    matches_after_first_final = len(not_final_matches_after_first_final)

    makespan = 0
    for i, r in enumerate(solution[::-1]):
        if r:
            makespan = len(solution) - i
            break
    
    first_not_filled_round = 0
    for i, r in enumerate(solution):
        if len(r) < matches_per_round:
            first_not_filled_round = i
            break

    # further down missing rounds is not as bad
    missing_cost = 0
    for i, r in enumerate(solution):
        missing = matches_per_round - len(r)
        missing_cost += missing * (makespan - i)
        # empty round not at the end is really bad
        if not r and i < makespan:
            missing_cost += 10000


    match_to_round = {}
    for i, r in enumerate(solution):
        for m in r:
            match_to_round[m] = i

    # player spread
    spread_cost = 0
    for player in players.itertuples():
        player_spread_cost = 0
        player_matches = player.Match_ID
        flattened = [match_id for r in solution for match_id in r]
        sorted_player_matches = sorted(list(player_matches), key=lambda m: flattened.index(m))
        for i in range(len(sorted_player_matches) - 1):
            match_1_r = match_to_round[sorted_player_matches[i]]
            match_2_r = match_to_round[sorted_player_matches[i + 1]]
            diff = match_2_r - match_1_r

            if diff < 3:
                player_spread_cost += -15*diff + 30
            else:
                player_spread_cost += 0.5*diff - 1.5

            spread_cost += player_spread_cost

    return 100 * spread_cost + missing_cost + makespan + 100 * 1/(matches_after_first_final + 1) + 100 * 1/(first_not_filled_round + 1)



def simulated_annealing(initial_solution, neighborhood_function, cost_function, T0, Tmin, alpha, max_iter, players, matches, matches_per_round):
    current = initial_solution
    current_cost = cost_function(current, players, matches, matches_per_round)

    best = current
    best_cost = current_cost

    T = T0

    print("Starting simulated annealing")
    print(f"T: {T}")

    for i in range(max_iter):
        if T < Tmin:
            break
        # generate neighbor
        candidate = neighborhood_function(current, players, matches, matches_per_round)
        candidate_cost = cost_function(candidate, players, matches, matches_per_round)

        delta_cost = candidate_cost - current_cost

        if delta_cost < 0 or random.random() < math.exp(-delta_cost / T):
            current = candidate
            current_cost = candidate_cost

            # track best solution
            if current_cost < best_cost:
                best = current
                best_cost = current_cost
                print(f"Better solution found with cost {best_cost}: {best}")
        
        # cool down
        T *= alpha
        if i % 10 == 0:
            print(f"T: {T}")
    
    return best, best_cost



def simulated_annealing_setup(players, matches, optimize_per_match, number_of_rounds, matches_per_round):
    # First create a default valid solution
    if optimize_per_match:
        s = []
        current_round = []
        matches = matches.sort_values(["Groep", "Onderdeel", "Nr"])
        for match_id in matches["ID"].tolist():
            prerequisites = get_match_parents_ID(matches, match_id)
            players_in_this_match = matches.loc[matches["ID"] == match_id, "Players"].iloc[0]
            total_matches_of_these_players = [m for name in players_in_this_match for m in players.loc[players["Naam"] == name, "Match_ID"].iloc[0]]
            if any(pre in current_round for pre in prerequisites) or len(current_round) == matches_per_round or any(m in current_round for m in total_matches_of_these_players):
                s.append(current_round)
                current_round = []
            current_round.append(match_id)
        s.append(current_round)
        if len(s) > number_of_rounds:
            print(f"No initial solution found, minimal number of rounds required: {len(s)}")
        elif len(s) < number_of_rounds:
            s.extend([[] for _ in range(number_of_rounds - len(s))])
        best, best_cost = simulated_annealing(s, swap_random_valid_match, match_cost, 100.0, 1e-3, 0.95, 10000, players, matches, matches_per_round)
        print("Best solution:")
        print(best)
    else:
        s = []
        matches = matches.sort_values(["Groep", "Onderdeel", "Nr"])
        onderdeel_rondes = matches[["Onderdeel", "Ronde"]].drop_duplicates()
        s = [onderdeel + " " + ronde for onderdeel, ronde in onderdeel_rondes.itertuples(index=False, name=None)]
        best, best_cost = simulated_annealing(s, swap_random_valid_ronde, ronde_cost, 100.0, 100.0, 0.95, 10000, players, matches, matches_per_round)
        print("Best solution:")
        print(best)