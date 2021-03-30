from flask import Flask, render_template
from flask.globals import request
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from nltk import RegexpTokenizer

app = Flask(__name__)

tokenizer = RegexpTokenizer(r'[a-z]+')

stopwords = set()

with open('stopwords.txt', encoding='utf8') as file:
    for line in file:
        stopwords.add(line.strip())

# https://stackoverflow.com/a/50312981

async def getContent(session, url):
    async with session.get(url) as response:
        return await response.text()

async def getContentOfUrls(urls):
    tasks = []
    async with aiohttp.ClientSession() as session:
        if type(urls)==str:
            tasks.append(getContent(session, urls))
        else:
            for url in urls:
                tasks.append(getContent(session, url))
        return await asyncio.gather(*tasks)

async def findWordFrequencies(html):
    html = BeautifulSoup(html, 'lxml')
    text = html.get_text()
    text = text.lower().strip()
    tokenized = tokenizer.tokenize(text)

    wordFrequencies = {}

    for word in tokenized:
        if len(word)<2:
            continue

        if word in wordFrequencies:
            wordFrequencies[word] += 1
        else:
            wordFrequencies[word] = 1

    return wordFrequencies

async def findKeywords(html):
    html = BeautifulSoup(html, 'lxml')
    text = html.get_text()
    text = text.lower().strip()
    tokenized = tokenizer.tokenize(text)

    wordFrequencies = {}

    for word in tokenized:
        if len(word)<2:
            continue

        if len(word)>45:
            continue
        
        if word in stopwords:
            continue

        if word in wordFrequencies:
            wordFrequencies[word] += 1
        else:
            wordFrequencies[word] = 1

    return wordFrequencies

# hitler geçme sayısı / toplam frekans sayısı nı kesişiyosa çarpıyoz
# etkisi artıyor

async def findSimilarity(url1Keywords, url2Keywords):
    url1KeywordsSet = set(dict(url1Keywords).keys())
    url2KeywordsSet = set(dict(url2Keywords).keys())
    
    intersection = len(url1KeywordsSet.intersection(url2KeywordsSet))

    return intersection / (len(url1KeywordsSet) + len(url2KeywordsSet) - intersection)

async def findSimilarityBetweenUrls(mainUrlContent, urlsContent):
    mainUrlKeywords = await findKeywords(mainUrlContent)
    
    keywordTasks = []
    for urlContent in urlsContent:
        keywordTasks.append(findKeywords(urlContent))

    keywords = await asyncio.gather(*keywordTasks)

    similarityTasks = []
    for urlKeywords in keywords:
        similarityTasks.append(findSimilarity(mainUrlKeywords, urlKeywords))

    similarities = await asyncio.gather(*similarityTasks)

    return similarities

@app.route('/stage1', methods=['POST', 'GET'])
def stage1():
    if request.method == 'POST':
        url = request.form.get('url-entry')

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        response = loop.run_until_complete(asyncio.gather(getContentOfUrls(url)))[0][0]
        keywords = loop.run_until_complete(asyncio.gather(findWordFrequencies(response)))[0]
        keywords = keywords.items()

        keywords = sorted(keywords, key=lambda tuple: tuple[1], reverse=True)

        return render_template('stage1.html', results = keywords)
    else:
        return render_template('stage1.html')

@app.route('/stage2', methods=['POST', 'GET'])
def stage2():
    if request.method == 'POST':
        url = request.form.get('url-entry')

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        response = loop.run_until_complete(asyncio.gather(getContentOfUrls(url)))[0][0]
        keywords = loop.run_until_complete(asyncio.gather(findKeywords(response)))[0]
        keywords = keywords.items()

        keywords = sorted(keywords, key=lambda tuple: tuple[1], reverse=True)

        keywords = keywords[:10]

        return render_template('stage2.html', results = keywords)
    else:
        return render_template('stage2.html')

@app.route('/stage3', methods=['POST', 'GET'])
def stage3():
    if request.method == 'POST':
        mainUrl = request.form.get('url-entry')
        urls = request.form.get('url-set').split('\n')
        urls = [url.strip() for url in urls]
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        mainUrlContent = loop.run_until_complete(asyncio.gather(getContentOfUrls(mainUrl)))[0][0]
        urlsContent = loop.run_until_complete(asyncio.gather(getContentOfUrls(urls)))[0]
        similarities = loop.run_until_complete(asyncio.gather(findSimilarityBetweenUrls(mainUrlContent, urlsContent)))[0]

        return render_template('stage3.html', results = zip(urls, similarities))
    else:
        return render_template('stage3.html')
