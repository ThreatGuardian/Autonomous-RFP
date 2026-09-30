import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";

const firebaseConfig = {
  apiKey: "AIzaSyCpfmXKg0bVw7wv4foDi897ILpWKLJtkgA",
  authDomain: "autonomous-rfp.firebaseapp.com",
  projectId: "autonomous-rfp",
  storageBucket: "autonomous-rfp.firebasestorage.app",
  messagingSenderId: "663761083176",
  appId: "1:663761083176:web:0674547dbc76f8b10e0e1d"
};

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
