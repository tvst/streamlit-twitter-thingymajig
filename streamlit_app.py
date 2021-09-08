from collections import defaultdict, namedtuple
from htbuilder import div, big, h2, styles
from htbuilder.units import rem
from math import floor
from nltk.corpus import stopwords
from textblob import TextBlob
import altair as alt
import datetime
import functools
import pandas as pd
import re
import streamlit as st
import time
import tweepy

prev_time = [time.time()]


# --------------------------------------------------------------------------------------------------
# Setup

@st.cache
def initial_setup():
    from textblob.download_corpora import download_all
    download_all()

    import nltk
    nltk.download("stopwords")

initial_setup()

auth = tweepy.AppAuthHandler(**st.secrets["twitter"])
twitter_api = tweepy.API(auth)

if "tweets" not in st.session_state:
    # These are all for debugging.
    st.session_state.tweets = []
    st.session_state.curr_tweet_page = 0
    st.session_state.curr_raw_tweet_page = 0


# --------------------------------------------------------------------------------------------------
# Useful functions for displaying stuff

COLOR_RED = "#FF4B4B"
COLOR_BLUE = "#1C83E1"
COLOR_CYAN = "#00C0F2"

def display_callout(title, color, icon):
    st.markdown(
        div(style=styles(
            background_color=color,
            padding=rem(1),
            display='flex',
            flex_direction='row',
            border_radius=rem(0.5),
            margin=(0, 0, rem(0.5), 0),
        ))(
            div(style=styles(font_size=rem(2), line_height=1))(
                icon
            ),
            div(style=styles(padding=(rem(0.5), 0, rem(0.5), rem(1))))(
                title
            ),
        )
        , unsafe_allow_html=True)

def display_small_text(text):
    st.markdown(
        div(style=styles(
            font_size=rem(0.8),
            margin=(0, 0, rem(1), 0),
        ))(
            text
        )
        , unsafe_allow_html=True)

def display_dial(title, value, color):
    st.markdown(
        div(style=styles(text_align="center", color=color, padding=(rem(0.8), 0, rem(3), 0)))(
            h2(style=styles(font_size=rem(0.8), font_weight=600, padding=0))(
                title
            ),
            big(style=styles(font_size=rem(3), font_weight=800, line_height=1))(
                value
            )
        )
        , unsafe_allow_html=True)

def display_dict(dict):
    for k, v in dict.items():
        a, b = st.columns([1, 4])
        a.write(f"**{k}:**")
        b.write(v)

def display_tweet(tweet):
    parsed_tweet = {
        "author": tweet.user.screen_name,
        "created_at": tweet.created_at,
        "url": get_tweet_url(tweet),
        "text": tweet.text,
    }
    display_dict(parsed_tweet)

def paginator(values, state_key, page_size):
    curr_page = getattr(st.session_state, state_key)

    a, b, c = st.columns(3)

    def decrement_page():
        curr_page = getattr(st.session_state, state_key)
        if curr_page > 0:
            setattr(st.session_state, state_key, curr_page - 1)

    def increment_page():
        curr_page = getattr(st.session_state, state_key)
        if curr_page + 1 < len(values) // page_size:
            setattr(st.session_state, state_key, curr_page + 1)

    def set_page(new_value):
        setattr(st.session_state, state_key, new_value - 1)

    a.write(" ")
    a.write(" ")
    a.button("Previous page", on_click=decrement_page)

    b.write(" ")
    b.write(" ")
    b.button("Next page", on_click=increment_page)

    c.selectbox(
        "Select a page",
        range(1, len(values) // page_size + 1),
        curr_page,
        on_change=set_page)

    curr_page = getattr(st.session_state, state_key)

    page_start = curr_page * page_size
    page_end = page_start + page_size

    return values[page_start:page_end]


# --------------------------------------------------------------------------------------------------
# Tweet-handling functions

def get_tweet_url(tweet):
    return f"https://twitter.com/{tweet.user.screen_name}/status/{tweet.id_str}"

STOP_WORDS_RE = re.compile(r"\b(?:" + "|".join(stopwords.words("english")) + r")\b", re.IGNORECASE)
TWEET_CRAP_RE = re.compile(r"\bRT\b", re.IGNORECASE)
URL_RE = re.compile(r"(^|\W)https?://[\w./&%]+\b", re.IGNORECASE)
PURE_NUMBERS_RE = re.compile(r"(^|\W)\$?[0-9]+\%?", re.IGNORECASE)
EMOJI_RE = re.compile("["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F1E0-\U0001F1FF"  # flags (iOS)
    "\U00002500-\U00002BEF"  # chinese char
    "\U00002702-\U000027B0"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\U0001f926-\U0001f937"
    "\U00010000-\U0010ffff"
    "\u2640-\u2642"
    "\u2600-\u2B55"
    "\u200d"
    "\u23cf"
    "\u23e9"
    "\u231a"
    "\ufe0f"  # dingbats
    "\u3030"
"]+", re.UNICODE)
OTHER_REMOVALS_RE = re.compile("["
    "\u2026"  # Ellipsis
"]+", re.UNICODE)
SHORTHAND_STOPWORDS_RE = re.compile(r"(?:^|\b)("
    "w|w/|"  # Short for "with"
    "bc|b/c|"  # Short for "because"
    "wo|w/o"  # Short for "without"
r")(?:\b|$)", re.IGNORECASE)
AT_MENTION_RE = re.compile(r"(^|\W)@\w+\b", re.IGNORECASE)
HASH_TAG_RE = re.compile(r"(^|\W)#\w+\b", re.IGNORECASE)
PREFIX_CHAR_RE = re.compile(r"(^|\W)[#@]", re.IGNORECASE)

def clean_tweet_text(text):
    regexes = [
        # AT_MENTION_RE,
        # HASH_TAG_RE,
        EMOJI_RE,
        PREFIX_CHAR_RE,
        PURE_NUMBERS_RE,
        STOP_WORDS_RE,
        TWEET_CRAP_RE,
        OTHER_REMOVALS_RE,
        SHORTHAND_STOPWORDS_RE,
        URL_RE,
    ]

    for regex in regexes:
        text = regex.sub("", text)
    return text

class UncacheableList(list):
    pass

cache_args = dict(
    show_spinner=False,
    allow_output_mutation=True,
    suppress_st_warning=True,
    hash_funcs={
        'streamlit.session_state.SessionState': lambda x: None,
        pd.DataFrame: lambda x: None,
        UncacheableList: lambda x: None,
    }
)

@st.cache(ttl=60*60, **cache_args)
def search_twitter(
        query_terms, days_ago, limit,
        exclude_replies, exclude_retweets,
        min_replies, min_retweets, min_faves):

    start_date = str(rel_to_abs_date(days_ago))

    query_list = [
        query_terms,
        " -RT" if exclude_retweets else "",
        f"since:{start_date}",
        "-filter:replies" if exclude_replies else "",
        "-filter:nativeretweets" if exclude_retweets else "",
        f"min_replies:{min_replies}",
        f"min_retweets:{min_retweets}",
        f"min_faves:{min_faves}",
    ]

    query_str = " ".join(query_list)

    tweets = UncacheableList(
        tweepy.Cursor(
            # TODO: Set up Premium search?
            twitter_api.search,
            q=query_str,
            lang="en",
            count=limit,
            include_entities=False,
        ).items(limit)
    )

    return tweets


@st.cache(**cache_args)
def munge_the_numbers(tweets, timestamp1, timestampN):  # Timestamps are just for cache-busting.

    word_counts = defaultdict(int)
    bigram_counts = defaultdict(int)
    trigram_counts = defaultdict(int)
    nounphrase_counts = defaultdict(int)
    sentiment_list = []

    SentimentListItem = namedtuple('SentimentListItem', ('date', 'polarity', 'subjectivity', 'url'))

    for tweet in tweets:
        clean_text = clean_tweet_text(tweet.text).lower()
        blob = TextBlob(clean_text)

        add_counts(word_counts, blob.word_counts)
        add_counts(bigram_counts, get_counts(blob.ngrams(2), key_sep=" "))
        add_counts(trigram_counts, get_counts(blob.ngrams(3), key_sep=" "))
        add_counts(nounphrase_counts, get_counts(blob.noun_phrases, key_sep=""))
        sentiment_list.append(SentimentListItem(
            tweet.created_at,
            blob.sentiment.polarity,
            blob.sentiment.subjectivity,
            get_tweet_url(tweet),
        ))

        # display_dict({
        #     "dirty text": tweet.text,
        #     "clean text": clean_text,
        #     "noun phrases": blob.noun_phrases,
        #     "sentiment": blob.sentiment,
        #     "word_count": blob.word_counts,
        #     "2-grams": get_counts(blob.ngrams(2)),
        #     "3-grams": get_counts(blob.ngrams(3)),
        # })

    def to_df(the_dict):
        items = the_dict.items()
        items = ((term, count, len(term.split(' '))) for (term, count) in items)
        return pd.DataFrame(items, columns=('term', 'count', 'num_words'))

    return {
        'word_counts': to_df(word_counts),
        'bigram_counts': to_df(bigram_counts),
        'trigram_counts': to_df(trigram_counts),
        'nounphrase_counts': to_df(nounphrase_counts),
        'sentiment_list': sentiment_list,
    }


# --------------------------------------------------------------------------------------------------
# Result aggregation functions

def add_counts(accumulator, ngrams):
    for ngram, count in ngrams.items():
        accumulator[ngram] += count

def get_counts(blobfield, key_sep):
    return {
        key_sep.join(x): blobfield.count(x)
        for x in blobfield
    }


# --------------------------------------------------------------------------------------------------
# Other utilities

def rel_to_abs_date(days):
    if days == None:
        return datetime.date(day=1, month=1, year=1970),
    return datetime.date.today() - datetime.timedelta(days=days)


# --------------------------------------------------------------------------------------------------
# Draw app inputs

"""
# Tweet analysis thingymajig!
"""

relative_dates = {
    "1 day ago": 1,
    "1 week ago": 7,
    "2 weeks ago": 14,
    "1 month ago": 30,
    "3 months ago": 90,
    "6 months ago": 180,
    "1 year ago": 365,
    "5 years ago": 365 * 5,
    "all time": None,
}

search_params = {}
search_params["query_terms"] = st.text_input("Search term", "streamlit")

a, b = st.columns([2, 1])
selected_rel_date = a.selectbox("Search from date", list(relative_dates.keys()), 3)
search_params["days_ago"] = relative_dates[selected_rel_date]
search_params["limit"]    = b.number_input("Limit", 1, None, 10000)

if search_params["days_ago"] > 30:
    with a:
        display_small_text("""
            ⚠️ To go past 30 days you need to pay for
            <a href='https://developer.twitter.com/en/products/twitter-api/premium-apis'>
            Twitter's Premium API</a>.
        """)

a, b, c = st.columns(3)
search_params["min_replies"]      = a.number_input("Minimum replies", 0, None, 0)
search_params["min_retweets"]     = b.number_input("Minimum retweets", 0, None, 0)
search_params["min_faves"]        = c.number_input("Minimum hearts", 0, None, 0)
search_params["exclude_replies"]  = a.checkbox("Exclude replies", False)
search_params["exclude_retweets"] = b.checkbox("Exclude retweets", False)

if not search_params["query_terms"]:
    st.stop()


# --------------------------------------------------------------------------------------------------
# Run some numbers...

tweets = search_twitter(**search_params)

if not tweets:
    "No results"
    st.stop()

results = munge_the_numbers(tweets, tweets[0].created_at, tweets[-1].created_at)


# --------------------------------------------------------------------------------------------------
# Draw results

"""
---

# Analysis results
"""
st.write("Number of matching tweets:", len(tweets))

"""
## Sentiment
"""

sentiment_df = pd.DataFrame(results['sentiment_list'])

polarity_color = COLOR_BLUE
subjectivity_color = COLOR_CYAN

a, b = st.columns(2)

with a:
    display_dial("POLARITY", f"{sentiment_df['polarity'].mean():.2f}", polarity_color)
with b:
    display_dial("SUBJECTIVITY", f"{sentiment_df['subjectivity'].mean():.2f}", subjectivity_color)

if search_params["days_ago"] <= 1:
    timeUnit = "hours"
elif search_params["days_ago"] <= 30:
    timeUnit = "monthdate"
else:
    timeUnit = "yearmonthdate"

chart = alt.Chart(sentiment_df, title="Sentiment Subjectivity")

avg_subjectivity = chart.mark_line(
    interpolate="catmull-rom",
    tooltip=True,
).encode(
    x=alt.X("date:T", timeUnit=timeUnit, title="date"),
    y=alt.Y("mean(subjectivity):Q", title="subjectivity", scale=alt.Scale(domain=[0, 1])),
    color=alt.Color(value=subjectivity_color),
)

subjectivity_values = chart.mark_point(
    tooltip=True,
    size=75,
    filled=True,
).encode(
    x=alt.X("date:T", timeUnit=timeUnit, title="date"),
    y=alt.Y("subjectivity:Q", title="subjectivity"),
    color=alt.Color(value=subjectivity_color + "88"),
    href="url",
)

chart = alt.Chart(sentiment_df, title="Sentiment Polarity")

avg_polarity = chart.mark_line(
    interpolate="catmull-rom",
    tooltip=True,
).encode(
    x=alt.X("date:T", timeUnit=timeUnit, title="date"),
    y=alt.Y("mean(polarity):Q", title="polarity", scale=alt.Scale(domain=[-1, 1])),
    color=alt.Color(value=polarity_color),
)

polarity_values = chart.mark_point(
    tooltip=True,
    size=75,
    filled=True,
).encode(
    x=alt.X("date:T", timeUnit=timeUnit, title="date"),
    y=alt.Y("polarity:Q", title="polarity"),
    color=alt.Color(value=polarity_color + "88"),
    href="url",
)

st.altair_chart(
    avg_polarity + polarity_values,
    use_container_width=True)

st.altair_chart(
    avg_subjectivity + subjectivity_values,
    use_container_width=True)

display_callout("Click on datapoints above to see the actual tweet!", "#F0F2F6", "👉")
display_small_text("HINT: You may want to <code>ctrl-click</code> or <code>cmd-click</code> to open in a new tab.")

" "


"""
## Top terms
"""

terms = pd.concat([
    results['word_counts'],
    results['bigram_counts'],
    results['trigram_counts'],
    results['nounphrase_counts'],
])

a, b = st.columns(2)
adjustment_factor = a.slider("Prioritize long expressions", 0.0, 1.0, 0.2, 0.001)
# Default value picked heuristically.

max_threshold = terms['count'].max()
threshold = b.slider("Threshold", 0.0, 1.0, 0.3) * max_threshold
# Default value picked heuristically.

weights = (
    (terms['num_words'] * adjustment_factor * (terms['count'] - 1))
    + terms['count']
)
# -1 to deprioritize items that only appear once.

filtered_terms = terms[weights > threshold]

st.altair_chart(
    alt.Chart(filtered_terms)
        .mark_bar(tooltip=True)
        .encode(
            x='count:Q',
            y=alt.Y('term:N', sort='-x'),
            color=alt.Color(value=COLOR_BLUE),
        ),
    use_container_width=True
)


"""
## Raw data
"""

def draw_count(label, df, init_filter_divider):
    xmax = int(floor(df['count'].max()))
    x = st.slider(label, 0, xmax, xmax // init_filter_divider)
    df = df[df['count'] > x]
    df = df.sort_values(by='count', ascending=False)
    df
    " "

if st.checkbox("Show term counts"):
    draw_count("Term count cut-off", terms, 5)

if st.checkbox("Show word counts"):
    draw_count("Word count cut-off", results['word_counts'], 5)

if st.checkbox("Show bigram counts"):
    draw_count("Bigram count cut-off", results['bigram_counts'], 3)

if st.checkbox("Show trigram counts"):
    draw_count("Trigram count cut-off", results['trigram_counts'], 2)

if st.checkbox("Show noun-phrase counts"):
    draw_count("Word count cut-off", results['nounphrase_counts'], 3)

if st.checkbox("Show tweets"):
    for result in paginator(tweets, "curr_tweet_page", 10):
        display_tweet(result)
        "---"

if st.checkbox("Show raw tweets"):
    for result in paginator(tweets, "curr_raw_tweet_page", 1):
        display_dict(result.__dict__)
        "---"
