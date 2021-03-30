from asyncio.windows_events import NULL
from flask import Flask, render_template
from flask.globals import request
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from nltk import RegexpTokenizer
from urllib.parse import urljoin
from nltk.corpus import wordnet

app = Flask(__name__)

tokenizer = RegexpTokenizer(r'[a-z]+')

stopwords = set()

subUrlLimit = 5

with open('stopwords.txt', encoding='utf8') as file:
    for line in file:
        stopwords.add(line.strip())

# https://stackoverflow.com/a/50312981

async def getContent(session, url):
    try:
        async with session.get(url) as response:
            return await response.text()
    except:
        return "error"

async def checkHead(session, url):
    try:
        async with session.head(url) as response:
            if response.status==200 and "html" in response.headers.get('Content-Type'):
                return url
            else:
                return None
    except:
        return None


async def getContentOfUrls(urls):
    tasks = []
    timeout = aiohttp.ClientTimeout(total=5)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        if type(urls)==str:
            tasks.append(getContent(session, urls))
        else:
            for url in urls:
                tasks.append(getContent(session, url))
        return await asyncio.gather(*tasks)

async def checkHeadOfUrls(urls):
    tasks = []
    results = []
    timeout = aiohttp.ClientTimeout(total=5)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        if type(urls)==str:
            tasks.append(checkHead(session, urls))
        else:
            for url in urls:
                tasks.append(checkHead(session, url))
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

    keywords = list(wordFrequencies.items())
    keywords = sorted(keywords, key=lambda tuple: tuple[1], reverse=True)
    keywords = keywords[:15]

    return keywords

def findSimilarWords(keywords):
    similarWords = set()

    for (keyword, frequency) in keywords:
        synsets = wordnet.synsets(keyword) 
        for syns in synsets: 
            for similarLemma in syns.lemmas():
                similarWord = similarLemma.name()

                if '_' in similarWord:
                    continue

                similarWord = similarWord.lower()
                
                if similarWord not in similarWords:
                    similarWords.add(similarWord)

    return similarWords

# hitler geçme sayısı / toplam frekans sayısı nı kesişiyosa çarpıyoz
# etkisi artıyor

async def findSimilarity(url1Keywords, url2Keywords):
    url1KeywordsSet = set(dict(url1Keywords).keys())
    url2KeywordsSet = set(dict(url2Keywords).keys())
    
    intersection = len(url1KeywordsSet.intersection(url2KeywordsSet))
    union = len(url1KeywordsSet) + len(url2KeywordsSet)

    return intersection / (union - intersection)

async def findSemanticSimilarity(url1Keywords, url2Keywords, url1Semantics, url2Semantics):
    url1KeywordsSet = set(dict(url1Keywords).keys())
    url2KeywordsSet = set(dict(url2Keywords).keys())
    
    intersection = len(url1KeywordsSet.intersection(url2KeywordsSet)) + len(url1Semantics.intersection(url2Semantics))
    union = len(url1KeywordsSet) + len(url2KeywordsSet) + len(url1Semantics) + len(url2Semantics)

    return intersection / (union - intersection)

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

    return similarities, mainUrlKeywords, keywords

async def findSemanticSimilarityBetweenUrls(mainUrlContent, urlsContent):
    mainUrlKeywords = await findKeywords(mainUrlContent)
    mainUrlSemantics = findSimilarWords(mainUrlKeywords)
    
    keywordTasks = []
    for urlContent in urlsContent:
        keywordTasks.append(findKeywords(urlContent))

    keywords = await asyncio.gather(*keywordTasks)

    allSemantics = []
    similarityTasks = []
    for urlKeywords in keywords:
        semantics = findSimilarWords(urlKeywords)
        allSemantics.append(semantics)
        similarityTasks.append(findSemanticSimilarity(mainUrlKeywords, urlKeywords, mainUrlSemantics, semantics))

    similarities = await asyncio.gather(*similarityTasks)

    return similarities, mainUrlKeywords, keywords, mainUrlSemantics, allSemantics

async def getSublinks(url):
    html = await asyncio.gather(getContentOfUrls(url))
    html = html[0][0]
    html = BeautifulSoup(html, 'lxml')

    subUrls = set()

    for link in html.findAll('a'):
        subUrl = str(link.get('href'))

        if subUrl==url:
            continue
        
        if not subUrl.startswith('http'):
            subUrl = urljoin(url, subUrl)

        if subUrl==url:
            continue

        if url+"#" in subUrl:
            continue

        subUrls.add(subUrl)

    subUrls = list(subUrls)

    subUrls = subUrls[:subUrlLimit+5]

    heads = await checkHeadOfUrls(subUrls)

    subUrls = [url for url in heads if url!=None]

    subUrls = subUrls[:subUrlLimit]

    return subUrls

async def generateSublinksTree(url, depth=0, tree=dict(), urlSet=set()):
    sublinks = await getSublinks(url)

    for sublink in sublinks:
        tree[sublink] = dict()
        urlSet.add(sublink)

    if depth<1:
        sublinkTasks = []
        for sublink in tree:
            sublinkTasks.append(generateSublinksTree(sublink, depth=depth+1, tree=tree[sublink], urlSet=urlSet))
        await asyncio.gather(*sublinkTasks)

@app.route('/stage1', methods=['POST', 'GET'])
def stage1():
    if request.method == 'POST':
        url = request.form.get('url-entry')

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        response = loop.run_until_complete(asyncio.gather(getContentOfUrls(url)))[0][0]
        wordFrequencies = loop.run_until_complete(asyncio.gather(findWordFrequencies(response)))[0]
        wordFrequencies = wordFrequencies.items()

        wordFrequencies = sorted(wordFrequencies, key=lambda tuple: tuple[1], reverse=True)

        return render_template('stage1.html', results = wordFrequencies)
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
        similarities, mainUrlKeywords, keywords = loop.run_until_complete(asyncio.gather(findSimilarityBetweenUrls(mainUrlContent, urlsContent)))[0]

        return render_template('stage3.html', results = zip(urls, similarities), mainUrl = mainUrl, mainUrlKeywords = mainUrlKeywords, keywords = dict(zip(urls, keywords)))
    else:
        return render_template('stage3.html')

@app.route('/stage4', methods=['POST', 'GET'])
def stage4():
    if request.method == 'POST':
        mainUrl = request.form.get('url-entry')
        urls = request.form.get('url-set').split('\n')
        urls = [url.strip() for url in urls]
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        mainUrlContent = loop.run_until_complete(asyncio.gather(getContentOfUrls(mainUrl)))[0][0]
        urlsContent = loop.run_until_complete(asyncio.gather(getContentOfUrls(urls)))[0]
        
        similarities, mainUrlKeywords, keywords = loop.run_until_complete(asyncio.gather(findSimilarityBetweenUrls(mainUrlContent, urlsContent)))[0]

        sublinksTree = dict()
        sublinksSet = set()

        for url in urls:
            sublinksTree[url] = {}

        loop.run_until_complete(asyncio.gather(*[generateSublinksTree(url, tree=sublinksTree[url], urlSet=sublinksSet) for url in urls]))

        sublinksContent = loop.run_until_complete(asyncio.gather(getContentOfUrls(sublinksSet)))[0]
        
        sublinkSimilarities, mainUrlKeywords, sublinkKeywords = loop.run_until_complete(asyncio.gather(findSimilarityBetweenUrls(mainUrlContent, sublinksContent)))[0]
        
        similaritiesAndSites = dict(zip(urls, similarities))
        sublinkAndSimilarities = dict(zip(sublinksSet, sublinkSimilarities))

        for site, subSites in sublinksTree.items():
            siteTotal = 0
            for subSite, subSubSites in subSites.items():
                subSubSiteTotal = 0
                for subSubSite in subSubSites:
                    sublinksTree[site][subSite][subSubSite]['similarity'] = round(sublinkAndSimilarities[subSubSite] * 100, 3)
                    subSubSiteTotal += sublinkAndSimilarities[subSubSite]
                subSubSiteTotal += sublinkAndSimilarities[subSite]
                sublinksTree[site][subSite]['similarity'] = round(subSubSiteTotal * 100, 3)
                siteTotal += subSubSiteTotal
            similaritiesAndSites[site] += siteTotal
            sublinksTree[site]['similarity'] = round(similaritiesAndSites[site] * 100, 3)

        sublinksTree = dict(sorted(sublinksTree.items(), key=lambda site: site[1]['similarity']))

        urlsAndKeywords = list(zip(urls, keywords))

        sublinkKeywords = dict(zip(sublinksSet, sublinkKeywords))

        return render_template('stage4.html', mainUrl = mainUrl, mainUrlKeywords = mainUrlKeywords, urlsAndKeywords = urlsAndKeywords, sublinksTree = sublinksTree, sublinksSet = sublinksSet, sublinkKeywords = sublinkKeywords)
    else:
        return render_template('stage4.html')

@app.route('/stage5', methods=['POST', 'GET'])
def stage5():
    if request.method == 'POST':
        mainUrl = request.form.get('url-entry')
        urls = request.form.get('url-set').split('\n')
        urls = [url.strip() for url in urls]
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        mainUrlContent = loop.run_until_complete(asyncio.gather(getContentOfUrls(mainUrl)))[0][0]
        urlsContent = loop.run_until_complete(asyncio.gather(getContentOfUrls(urls)))[0]
        
        similarities, mainUrlKeywords, keywords, mainUrlSemantics, semantics = loop.run_until_complete(asyncio.gather(findSemanticSimilarityBetweenUrls(mainUrlContent, urlsContent)))[0]

        sublinksTree = dict()
        sublinksSet = set()

        for url in urls:
            sublinksTree[url] = {}

        loop.run_until_complete(asyncio.gather(*[generateSublinksTree(url, tree=sublinksTree[url], urlSet=sublinksSet) for url in urls]))

        sublinksContent = loop.run_until_complete(asyncio.gather(getContentOfUrls(sublinksSet)))[0]
        
        sublinkSimilarities, mainUrlKeywords, sublinkKeywords, mainUrlSemantics, sublinkSemantics = loop.run_until_complete(asyncio.gather(findSemanticSimilarityBetweenUrls(mainUrlContent, sublinksContent)))[0]
        
        similaritiesAndSites = dict(zip(urls, similarities))
        sublinkAndSimilarities = dict(zip(sublinksSet, sublinkSimilarities))

        for site, subSites in sublinksTree.items():
            siteTotal = 0
            for subSite, subSubSites in subSites.items():
                subSubSiteTotal = 0
                for subSubSite in subSubSites:
                    sublinksTree[site][subSite][subSubSite]['similarity'] = round(sublinkAndSimilarities[subSubSite] * 100, 3)
                    subSubSiteTotal += sublinkAndSimilarities[subSubSite]
                subSubSiteTotal += sublinkAndSimilarities[subSite]
                sublinksTree[site][subSite]['similarity'] = round(subSubSiteTotal * 100, 3)
                siteTotal += subSubSiteTotal
            similaritiesAndSites[site] += siteTotal
            sublinksTree[site]['similarity'] = round(similaritiesAndSites[site] * 100, 3)

        sublinksTree = dict(sorted(sublinksTree.items(), key=lambda site: site[1]['similarity']))
        
        urlsAndKeywords = list(zip(urls, keywords))
        sublinkKeywords = dict(zip(sublinksSet, sublinkKeywords))

        urlsAndSemantics = list(zip(urls, semantics))
        sublinkAndSemantics = dict(zip(sublinksSet, sublinkSemantics))

        return render_template('stage5.html', mainUrl = mainUrl, mainUrlSemantics = mainUrlSemantics, mainUrlKeywords = mainUrlKeywords, urlsAndKeywords = urlsAndKeywords, sublinksTree = sublinksTree, sublinksSet = sublinksSet, sublinkKeywords = sublinkKeywords, urlsAndSemantics=urlsAndSemantics, sublinkAndSemantics=sublinkAndSemantics)
    else:
        return render_template('stage5.html')