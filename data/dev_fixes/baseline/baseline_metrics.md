### rc4_offline

| lang | split | block | n | cat F1 | cat acc | pri F1 | pri acc |
|---|---|---|---|---|---|---|---|
| en | tune | headline | 20 | 0.814 | 0.800 | 0.733 | 0.750 |
| en | tune | implicit_urgency | 10 | 0.915 | 0.900 | 0.200 | 0.429 |
| en | tune | probe | 6 | 0.542 | 0.600 | 1.000 | 1.000 |
| en | tune | all | 36 | 0.795 | 0.800 | 0.727 | 0.719 |
| en | check | headline | 20 | 0.901 | 0.900 | 0.592 | 0.650 |
| en | check | implicit_urgency | 10 | 0.771 | 0.900 | 0.300 | 0.429 |
| en | check | probe | 6 | 0.667 | 0.800 | 0.444 | 0.800 |
| en | check | all | 36 | 0.884 | 0.886 | 0.632 | 0.625 |
| en | all | headline | 40 | 0.858 | 0.850 | 0.671 | 0.700 |
| en | all | implicit_urgency | 20 | 0.760 | 0.900 | 0.200 | 0.429 |
| en | all | probe | 12 | 0.571 | 0.700 | 0.804 | 0.900 |
| en | all | all | 72 | 0.841 | 0.843 | 0.681 | 0.672 |
| ar | tune | headline | 20 | 0.813 | 0.800 | 0.852 | 0.850 |
| ar | tune | implicit_urgency | 10 | 0.581 | 0.700 | 0.259 | 0.375 |
| ar | tune | probe | 6 | 0.333 | 0.400 | 0.444 | 0.800 |
| ar | tune | all | 36 | 0.701 | 0.714 | 0.718 | 0.727 |
| ar | check | headline | 20 | 0.780 | 0.800 | 0.722 | 0.750 |
| ar | check | implicit_urgency | 10 | 0.714 | 0.900 | 0.259 | 0.375 |
| ar | check | probe | 6 | 0.367 | 0.600 | 0.375 | 0.600 |
| ar | check | all | 36 | 0.744 | 0.800 | 0.624 | 0.636 |
| ar | all | headline | 40 | 0.798 | 0.800 | 0.786 | 0.800 |
| ar | all | implicit_urgency | 20 | 0.648 | 0.800 | 0.259 | 0.375 |
| ar | all | probe | 12 | 0.400 | 0.500 | 0.412 | 0.700 |
| ar | all | all | 72 | 0.726 | 0.757 | 0.671 | 0.682 |
| az | tune | headline | 20 | 0.757 | 0.750 | 0.635 | 0.650 |
| az | tune | implicit_urgency | 10 | 0.483 | 0.667 | 0.667 | 0.750 |
| az | tune | probe | 6 | 0.267 | 0.500 | 1.000 | 1.000 |
| az | tune | all | 36 | 0.683 | 0.697 | 0.712 | 0.719 |
| az | check | headline | 20 | 0.650 | 0.650 | 0.713 | 0.750 |
| az | check | implicit_urgency | 10 | 0.493 | 0.700 | 0.167 | 0.222 |
| az | check | probe | 6 | 0.300 | 0.400 | 0.375 | 0.600 |
| az | check | all | 36 | 0.649 | 0.629 | 0.573 | 0.588 |
| az | all | headline | 40 | 0.707 | 0.700 | 0.673 | 0.700 |
| az | all | implicit_urgency | 20 | 0.498 | 0.684 | 0.311 | 0.471 |
| az | all | probe | 12 | 0.333 | 0.444 | 0.438 | 0.778 |
| az | all | all | 72 | 0.666 | 0.662 | 0.648 | 0.651 |
| all | tune | headline | 60 | 0.792 | 0.783 | 0.738 | 0.750 |
| all | tune | implicit_urgency | 30 | 0.506 | 0.759 | 0.318 | 0.522 |
| all | tune | probe | 18 | 0.490 | 0.500 | 0.813 | 0.929 |
| all | tune | all | 108 | 0.730 | 0.738 | 0.722 | 0.722 |
| all | check | headline | 60 | 0.790 | 0.783 | 0.676 | 0.717 |
| all | check | implicit_urgency | 30 | 0.625 | 0.833 | 0.222 | 0.333 |
| all | check | probe | 18 | 0.366 | 0.600 | 0.400 | 0.667 |
| all | check | all | 108 | 0.766 | 0.771 | 0.609 | 0.616 |
| all | all | headline | 120 | 0.790 | 0.783 | 0.708 | 0.733 |
| all | all | implicit_urgency | 60 | 0.577 | 0.797 | 0.270 | 0.425 |
| all | all | probe | 36 | 0.439 | 0.552 | 0.565 | 0.793 |
| all | all | all | 216 | 0.749 | 0.755 | 0.667 | 0.668 |

Routing (set sizes, all languages): category {"2": 41, ">=3": 75, "1": 100}; priority {"1": 216}

Flag rates (all): {"distress": 0.0046, "empty_set": 0.0417, "injection_attempt": 0.0231, "safety": 0.0417}

High recall per family (all): {"__all_high__": {"n": 74, "high_recall": 0.3919}, "account_compromise": {"n": 6, "high_recall": 0.0}, "deadline_24h": {"n": 6, "high_recall": 0.1667}, "other_high": {"n": 5, "high_recall": 0.4}, "outage": {"n": 10, "high_recall": 0.4}, "physical_emergency": {"n": 8, "high_recall": 0.875}, "transport_danger": {"n": 7, "high_recall": 0.2857}}

### rc4_llm

| lang | split | block | n | cat F1 | cat acc | pri F1 | pri acc |
|---|---|---|---|---|---|---|---|
| en | tune | headline | 20 | 0.814 | 0.800 | 0.733 | 0.750 |
| en | tune | implicit_urgency | 10 | 0.915 | 0.900 | 0.200 | 0.429 |
| en | tune | probe | 6 | 0.542 | 0.600 | 1.000 | 1.000 |
| en | tune | all | 36 | 0.795 | 0.800 | 0.727 | 0.719 |
| en | check | headline | 20 | 0.901 | 0.900 | 0.592 | 0.650 |
| en | check | implicit_urgency | 10 | 0.771 | 0.900 | 0.300 | 0.429 |
| en | check | probe | 6 | 0.667 | 0.800 | 0.444 | 0.800 |
| en | check | all | 36 | 0.884 | 0.886 | 0.632 | 0.625 |
| en | all | headline | 40 | 0.858 | 0.850 | 0.671 | 0.700 |
| en | all | implicit_urgency | 20 | 0.760 | 0.900 | 0.200 | 0.429 |
| en | all | probe | 12 | 0.571 | 0.700 | 0.804 | 0.900 |
| en | all | all | 72 | 0.841 | 0.843 | 0.681 | 0.672 |
| ar | tune | headline | 20 | 0.813 | 0.800 | 0.852 | 0.850 |
| ar | tune | implicit_urgency | 10 | 0.581 | 0.700 | 0.259 | 0.375 |
| ar | tune | probe | 6 | 0.333 | 0.400 | 0.444 | 0.800 |
| ar | tune | all | 36 | 0.701 | 0.714 | 0.718 | 0.727 |
| ar | check | headline | 20 | 0.780 | 0.800 | 0.722 | 0.750 |
| ar | check | implicit_urgency | 10 | 0.714 | 0.900 | 0.259 | 0.375 |
| ar | check | probe | 6 | 0.367 | 0.600 | 0.375 | 0.600 |
| ar | check | all | 36 | 0.744 | 0.800 | 0.624 | 0.636 |
| ar | all | headline | 40 | 0.798 | 0.800 | 0.786 | 0.800 |
| ar | all | implicit_urgency | 20 | 0.648 | 0.800 | 0.259 | 0.375 |
| ar | all | probe | 12 | 0.400 | 0.500 | 0.412 | 0.700 |
| ar | all | all | 72 | 0.726 | 0.757 | 0.671 | 0.682 |
| az | tune | headline | 20 | 0.948 | 0.950 | 0.635 | 0.650 |
| az | tune | implicit_urgency | 10 | 0.550 | 0.778 | 0.667 | 0.750 |
| az | tune | probe | 6 | 0.600 | 0.750 | 1.000 | 1.000 |
| az | tune | all | 36 | 0.877 | 0.879 | 0.712 | 0.719 |
| az | check | headline | 20 | 0.901 | 0.900 | 0.713 | 0.750 |
| az | check | implicit_urgency | 10 | 0.667 | 0.800 | 0.167 | 0.222 |
| az | check | probe | 6 | 0.233 | 0.400 | 0.375 | 0.600 |
| az | check | all | 36 | 0.804 | 0.800 | 0.573 | 0.588 |
| az | all | headline | 40 | 0.930 | 0.925 | 0.673 | 0.700 |
| az | all | implicit_urgency | 20 | 0.543 | 0.789 | 0.311 | 0.471 |
| az | all | probe | 12 | 0.400 | 0.556 | 0.438 | 0.778 |
| az | all | all | 72 | 0.840 | 0.838 | 0.648 | 0.651 |
| all | tune | headline | 60 | 0.856 | 0.850 | 0.738 | 0.750 |
| all | tune | implicit_urgency | 30 | 0.519 | 0.793 | 0.318 | 0.522 |
| all | tune | probe | 18 | 0.555 | 0.571 | 0.813 | 0.929 |
| all | tune | all | 108 | 0.790 | 0.796 | 0.722 | 0.722 |
| all | check | headline | 60 | 0.870 | 0.867 | 0.676 | 0.717 |
| all | check | implicit_urgency | 30 | 0.640 | 0.867 | 0.222 | 0.333 |
| all | check | probe | 18 | 0.353 | 0.600 | 0.400 | 0.667 |
| all | check | all | 108 | 0.820 | 0.829 | 0.609 | 0.616 |
| all | all | headline | 120 | 0.862 | 0.858 | 0.708 | 0.733 |
| all | all | implicit_urgency | 60 | 0.590 | 0.831 | 0.270 | 0.425 |
| all | all | probe | 36 | 0.465 | 0.586 | 0.565 | 0.793 |
| all | all | all | 216 | 0.806 | 0.812 | 0.667 | 0.668 |

Routing (set sizes, all languages): category {"2": 51, ">=3": 55, "1": 110}; priority {"1": 216}

Flag rates (all): {"distress": 0.0046, "empty_set": 0.0417, "injection_attempt": 0.0231, "safety": 0.0417}

High recall per family (all): {"__all_high__": {"n": 74, "high_recall": 0.3919}, "account_compromise": {"n": 6, "high_recall": 0.0}, "deadline_24h": {"n": 6, "high_recall": 0.1667}, "other_high": {"n": 5, "high_recall": 0.4}, "outage": {"n": 10, "high_recall": 0.4}, "physical_emergency": {"n": 8, "high_recall": 0.875}, "transport_danger": {"n": 7, "high_recall": 0.2857}}
