const express=require('express');const cors=require('cors');const app=express();app.use(cors());app.use(express.json({limit:'2mb'}));
app.get('/health',(_,res)=>res.json({status:'ok',service:'newq-node-api'}));
app.post('/api/analyze',(req,res)=>{const {exam='UPSC',content='',question_count=5}=req.body||{};if(!content.trim())return res.status(400).json({error:'content is required'});res.json({status:'received',exam,question_count,message:'Node API ready. Connect this endpoint to the Python AI service.'});});
app.listen(process.env.PORT||3000,()=>console.log('NewQ Node backend running on port 3000'));
