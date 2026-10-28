export const DEMO_MODE = false;
export const API_BASE_URL = 'http://10.41.181.17:8000';

// Expo's fetch implementation supports multipart FormData uploads on
// current React Native versions where the built-in fetch throws
// "Unsupported FormDataPart implementation".
import { FormData as ExpoFormData, fetch as expoFetch } from 'expo/fetch';

const SAMPLE = {
  app:'NewQ', version:'0.1-mobile-demo', relevance:'HIGH', relevance_score:0.91,
  subject:'Economy', topic:'Monetary Policy',
  keywords:['RBI','monetary policy','inflation','liquidity','price stability','economic growth'],
  summary:['The Reserve Bank of India announced a new monetary policy framework aimed at maintaining price stability and supporting economic growth.'],
  signals:['Exam-topic match','Current-affairs relevance','Domain keywords detected']
};

function classify(content){
  const t=content.toLowerCase();
  if(/rbi|monetary policy|repo rate|liquidity|inflation/.test(t)) return ['Economy','Monetary Policy'];
  if(/isro|satellite|space mission|launch vehicle/.test(t)) return ['Science & Technology','Space Technology'];
  if(/climate|carbon|emission|global warming/.test(t)) return ['Environment','Climate Change'];
  if(/government scheme|yojana|beneficiary/.test(t)) return ['Government Schemes','Government Schemes'];
  if(/parliament|constitution|supreme court|minister|bill|governance/.test(t)) return ['Polity','Constitution & Governance'];
  return ['Current Affairs','General Current Affairs'];
}

function questions(content){
  const [subject,topic]=classify(content);
  if(topic==='Monetary Policy') return [
    {id:'q1',type:'Objective / Purpose',difficulty:'Easy',question:'What is the primary objective of the monetary policy framework described in the news?',options:['Maintaining price stability','Increasing import dependence','Eliminating financial regulation','Reducing all public expenditure'],answer:'Maintaining price stability',explanation:'The source states that the framework is aimed at maintaining price stability while supporting economic growth.'},
    {id:'q2',type:'Topic Classification',difficulty:'Easy',question:'Which topic is most directly represented by this news article?',options:['Monetary Policy','Tourism Management','Sports Administration','Cultural Heritage'],answer:'Monetary Policy',explanation:'The article discusses monetary policy, liquidity management, inflation and financial stability.'},
    {id:'q3',type:'News Fact',difficulty:'Medium',question:'Which institution is associated with the monetary policy announcement in the article?',options:['Reserve Bank of India','NITI Aayog','Ministry of External Affairs','SEBI'],answer:'Reserve Bank of India',explanation:'The article identifies the Reserve Bank of India as the institution announcing the measures.'},
    {id:'q4',type:'Conceptual',difficulty:'Medium',question:'Which of the following is directly associated with the monetary policy context discussed in the article?',options:['Liquidity management','Cultural preservation','Tourism promotion','Sports administration'],answer:'Liquidity management',explanation:'The source specifically mentions maintaining adequate liquidity as part of the policy framework.'},
    {id:'q5',type:'Source Grounded',difficulty:'Medium',question:'Which combination best represents the focus of the policy described in the news?',options:['Price stability, liquidity and financial stability','Tourism, exports and sports','Defence, agriculture and tourism','Education, culture and transport'],answer:'Price stability, liquidity and financial stability',explanation:'These areas are explicitly described as key elements of the policy measures in the source.'}
  ];
  return [
    {id:'q1',type:'Topic Classification',difficulty:'Easy',question:'Which topic is most directly represented by this news article?',options:[topic,'Sports Administration','Tourism Management','Cultural Heritage'],answer:topic,explanation:`The article is classified under ${topic}.`},
    {id:'q2',type:'Subject Identification',difficulty:'Medium',question:'Which subject area best matches this news?',options:[subject,'Sports','Entertainment','Tourism'],answer:subject,explanation:`The detected subject is ${subject}.`}
  ];
}

export async function analyzeNews(content,exam,count=5){
  const response = await fetch(`${API_BASE_URL}/api/analyze`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      exam,
      content,
      question_count: Math.max(3, Math.min(5, count)),
    }),
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const message =
      data.detail ||
      data.error ||
      `Backend error: ${response.status}`;

    throw new Error(
      typeof message === 'string' ? message : JSON.stringify(message)
    );
  }

  if (!Array.isArray(data.questions)) {
    throw new Error('The API response did not contain a valid questions array.');
  }

  console.log('[NewQ] API response received:', {
  version: data.version,
  exam: data.exam,
  question_count: data.question_count,
  actual_questions: data.questions.length,
  confidence_note: data.confidence_note,
});

  return {
    ...data,
    questions: data.questions.map((question, index) => ({
      ...question,
      id: question.id || `q${index + 1}`,
    })),
  };
}

// Maximum image size accepted by POST /api/extract-text (backend limit).
const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
const IMAGE_MIME_BY_EXTENSION = {
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  png: 'image/png',
  webp: 'image/webp',
  heic: 'image/heic',
};

export function guessImageMime(imageUri) {
  const cleanUri = String(imageUri || '').split('?')[0];
  const extension = cleanUri.split('.').pop().toLowerCase();
  return IMAGE_MIME_BY_EXTENSION[extension] || 'image/jpeg';
}

export async function extractTextFromImage(imageUri) {
  const mime = guessImageMime(imageUri);
  const fileName = `news-photo.${mime.split('/')[1].split('-')[0]}`;

  const formData = new ExpoFormData();
  formData.append('file', {
    uri: String(imageUri),
    name: fileName,
    type: mime,
  });

  const response = await expoFetch(`${API_BASE_URL}/api/extract-text`, {
    method: 'POST',
    body: formData,
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const message =
      data.detail ||
      data.error ||
      `Backend error: ${response.status}`;

    throw new Error(
      typeof message === 'string' ? message : JSON.stringify(message)
    );
  }

  if (typeof data.text !== 'string' || !data.text.trim()) {
    throw new Error(
      'No readable article text was found in this image.'
    );
  }

  return data;
}

export async function fetchNewsFeed() {
  const response = await fetch(`${API_BASE_URL}/api/news-feed`);

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const message =
      data.detail ||
      data.error ||
      `Backend error: ${response.status}`;

    throw new Error(
      typeof message === 'string' ? message : JSON.stringify(message)
    );
  }

  if (!Array.isArray(data.items)) {
    throw new Error(
      'The feed response did not contain a valid items list.'
    );
  }

  return data;
}
