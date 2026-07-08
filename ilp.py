# rules:
# Finals as late as possible
# X Not too many matches per round
# X Each match only in one round
# X Matches played in the right order (halve before finale)
# Matches played as early as possible
# X No player playing in two matches in the same round
import itertools

from pulp import LpMinimize, LpProblem, LpVariable, lpSum, LpAffineExpression

from simulated_annealing import get_match_parents_ID


def ilp(players, matches):
    number_of_rounds = 10
    matches_per_round = 2

    model = LpProblem("Scheduler_Problem", LpMinimize)
    # one variable per match per round

    # indexed based on match ID and based on round index
    match_variables = {
        match_i: {
            round_j: LpVariable(f"x_m{match_i}_r{round_j}", cat="Binary")
            for round_j in range(number_of_rounds)
        }
        for match_i in matches["ID"]
    }

    # each match only planned once
    for (match_i, round_j) in match_variables.items():
        model += lpSum(round_j.values()) == 1, f"match_{match_i}_once"

    # each round cannot have too many matches
    for round_j in range(number_of_rounds):
        model += lpSum(match_variables[x][round_j] for x in
                       match_variables) <= matches_per_round, f"max_matches_in_round_{round_j}"

    # a player cannot play two matches in the same round
    for player in players.itertuples():
        for (match_1, match_2) in itertools.combinations(player.Match_ID, 2):
            match_1_vars = match_variables[match_1]
            match_2_vars = match_variables[match_2]
            for index_in_player_matches in match_1_vars.keys():
                model += match_1_vars[index_in_player_matches] + match_2_vars[
                    index_in_player_matches] <= 1, f"{player.Naam}_not_playing_{match_1}_{match_2}_both_in_round_{index_in_player_matches}"

    # a match can only be played if it's two parents are played
    for match in matches[matches["Groep"] == "N/A"].itertuples():
        parent_ids = get_match_parents_ID(matches, match.ID)
        for parent_id in parent_ids:
            # parent needs to be scheduled before this match
            # the round of a match can be calculated as sum(index_in_player_matches * x_i), as only one of the x_i will be 1
            parent_round = lpSum(match_variables[parent_id][index_in_player_matches] * index_in_player_matches for
                                 index_in_player_matches in match_variables[parent_id].keys())
            match_round = lpSum(
                match_variables[match.ID][index_in_player_matches] * index_in_player_matches for index_in_player_matches
                in match_variables[match.ID].keys())
            model += parent_round + 1 <= match_round, f"match_{parent_id}_before_{match.ID}"

    optimum = 3
    under_value = 3
    over_value = 1

    # add optimization function
    optimization = LpAffineExpression()
    for player in players.itertuples():
        rounds_played_in = {match_id: lpSum(
            match_variables[match_id][index_in_player_matches] * index_in_player_matches for index_in_player_matches in
            match_variables[match_id].keys()) for match_id in player.Match_ID}
        for (round_1_id, round_2_id) in itertools.combinations(rounds_played_in, 2):
            # create a variable that is the absolute difference between the two rounds
            diff = LpVariable(f"diff_{player}_{round_1_id}_{round_2_id}", lowBound=0)
            model += diff >= rounds_played_in[round_1_id] - rounds_played_in[round_2_id]
            model += diff >= -(rounds_played_in[round_1_id] - rounds_played_in[round_2_id])
            diff_under_optimum = LpVariable(f"diff_{player}_{round_1_id}_{round_2_id}_under", lowBound=0)
            model += diff_under_optimum >= optimum - diff
            model += diff_under_optimum >= 0
            diff_over_optimum = LpVariable(f"diff_{player}_{round_1_id}_{round_2_id}_over", lowBound=0)
            model += diff_over_optimum >= diff - optimum
            model += diff_over_optimum >= 0

            optimization += under_value * diff_under_optimum + over_value * diff_over_optimum

    model += optimization

    model.solve()

    match_to_round = {}
    for match_id, rounds in match_variables.items():
        # only one of these should be 1
        rounds_scheduled = [k for k, v in rounds.items() if v.value() == 1]
        assert len(rounds_scheduled) == 1
        scheduled_in = rounds_scheduled[0]
        match_to_round[match_id] = scheduled_in

    highest_scheduled_round = max(match_to_round.values())
    rounds_to_matches = [[] for _ in range(highest_scheduled_round + 1)]
    for match, round in match_to_round.items():
        rounds_to_matches[round].append(match)

    return match_to_round, rounds_to_matches